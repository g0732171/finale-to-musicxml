"""Structural MUS reader using finale-file-parser 0.4.0's record decoders.

Recognise framed raw/DCL pools and zlib record pools by their bytes. Decode all
four layers; validate every active frame before pruning database history.
Never rewrite inputs, guess missing entries, or remove a referenced bad frame.
"""
from pathlib import Path
from finale_file_parser.errors import FinaleFileError


def _compact_slots(data, order):
    """Return whole live slots, or None for any malformed first slot."""
    from finale_file_parser.enigma import mus_entries as entries
    if not data or len(data) % 38:
        return None
    result = bytearray()
    position = 0
    while position < len(data):
        slot = data[position:position + 38]
        if int.from_bytes(slot[:4], order) > 0 and slot[4:] == bytes(34):
            position += 38
            continue
        count = int.from_bytes(slot[24:26], order)
        if (slot[4:6] != bytes(2) or count > 12 or
                not int.from_bytes(slot[18:22], order) & 0x80000000):
            return None
        span = 38 * entries._slot_span(count)
        if position + span > len(data):
            return None
        # Continuation slots belong to the same entry and cannot be discarded.
        for index in range(1, span // 38):
            tail = data[position + index * 38:position + (index + 1) * 38]
            if tail[:4] != slot[:4] or int.from_bytes(tail[4:6], order) != index:
                return None
        result.extend(data[position:position + span])
        position += span
    return bytes(result)


class MusStructureError(ValueError):
    pass


def _pools(path):
    from finale_file_parser.enigma import mus_payload as payload
    data = Path(path).read_bytes()
    if len(data) > 20 * 1024**2:
        raise MusStructureError('MUS input too large')
    # The pre-DCL container uses the same bounded framing with kinds 1..4,
    # six-byte headers and uncompressed payloads. Require the complete chain.
    for order in ('big', 'little'):
        if int.from_bytes(data[512:514], order) != 1:
            continue
        position = 512
        found = []
        for expected in (1, 2, 3, 4):
            if position + 6 > len(data):
                break
            kind = int.from_bytes(data[position:position+2], order)
            length = int.from_bytes(data[position+2:position+6], order)
            if kind != expected or length < 6 or position + length > len(data):
                break
            found.append(payload.MusPool(data[position+6:position+length], order, kind+14))
            position += length
        if len(found) == 4 and position == len(data):
            return tuple(found), 'raw-rows'
        raise MusStructureError('Malformed uncompressed MUS pool chain')
    pools = payload.read_mus_pools(path)
    return pools, 'dcl-rows' if all(p.kind is not None for p in pools) else 'zlib-records'


def _entries(pools):
    from finale_file_parser.enigma import mus_entries as entries
    from dataclasses import replace
    labelled = [p for p in pools if p.kind == 17]
    candidates = []
    for pool in labelled or pools:
        cleaned = _compact_slots(pool.data, pool.byte_order)
        if cleaned and entries._looks_like_entry_pool(cleaned, pool.byte_order):
            records = entries._read_pool(cleaned, pool.byte_order)
            position = 0
            corrected = []
            for record in records:
                flag = int.from_bytes(cleaned[position+18:position+22],pool.byte_order)
                count = int.from_bytes(cleaned[position+24:position+26],pool.byte_order)
                # NOTEBIT identifies sounding notes. A manually positioned rest
                # may store one fake note solely for its vertical placement.
                # Preserve its duration; never export that placement as pitch.
                if not flag & 0x40000000:
                    fields = dict(record.fields)
                    fields['numNotes'] = '0'
                    fields.pop('note',None)
                    record = replace(record,fields=fields)
                corrected.append(record)
                position += 38 * entries._slot_span(count)
            candidates.append(tuple(corrected))
    if len(candidates) != 1:
        raise MusStructureError('No unique valid MUS entry pool')
    return candidates[0]


def _texts(pools, fallback):
    from finale_file_parser.enigma import mus_document as decoder
    from finale_file_parser.enigma.document import Record
    if len(pools) != 4:
        raise MusStructureError('Unexpected MUS pool count')
    result = []
    seen = set()
    for match in decoder._TEXT_SECTION.finditer(pools[3].data):
        tag = match.group(1).decode('ascii')
        number = match.group(2).decode('ascii')
        if tag == 'fileInfo':
            kind = decoder._FILE_INFO_TYPES.get(match.group(2))
            if kind is None:
                continue
            identity, attrs = (tag, kind), {'type':kind}
        else:
            identity, attrs = (tag, number), {'number':number}
        if identity in seen:
            continue
        seen.add(identity)
        result.append(Record(tag, attrs, decoder._decode(match.group(3), fallback), {}))
    return tuple(result)


def _gfhold(raw, order, layout):
    from finale_file_parser.enigma.document import Record
    # ETF rows: clef, flags, four frame ids, clef percentage. The extended
    # record puts the percentage before the frame array. Each is a known
    # layout, not an offset search. Resolve ambiguity against the full graph.
    if len(raw.payload) != 20:
        raise MusStructureError('Unknown MUS frame-hold record length')
    if layout == 'etf':
        offsets, clef_at = (4,6,8,10), 0
    else:
        offsets, clef_at = (6,8,10,12), 0
    if any(raw.payload[14:]):
        raise MusStructureError('Unknown MUS frame-hold extension')
    percent_at = 12 if layout == 'etf' else 4
    percent = int.from_bytes(raw.payload[percent_at:percent_at+2], order)
    if percent > 1000:
        raise MusStructureError('Clef percentage is outside supported layout bounds')
    fields = {'clefID':str(int.from_bytes(raw.payload[clef_at:clef_at+2], order))}
    for layer, offset in enumerate(offsets, 1):
        frame = int.from_bytes(raw.payload[offset:offset+2], order)
        if frame:
            fields[f'frame{layer}'] = str(frame)
    return Record('gfhold', {'cmper1':str(raw.cmper1 if hasattr(raw,'cmper1') else raw.cmper),
                            'cmper2':str(raw.cmper2)}, '', fields)


def _normalise(doc):
    from finale_file_parser.enigma.document import DetailsPool, EntriesPool
    from finale_file_parser.enigma.location import (
        MalformedScoreError, _Placements, _place_frame_entries, effective_keys,
    )
    keys = effective_keys(doc)
    if not keys:
        raise MalformedScoreError('MUS document has no measures')
    last = max(keys)
    kept = []
    for record in doc.details.records:
        if record.tag == 'gfhold':
            if int(record.attrs['cmper1']) == 32767:
                continue
            frames = any(record.fields.get(f'frame{i}') not in (None,'','0') for i in range(1,5))
            if int(record.attrs['cmper2']) > last and not frames:
                continue
        kept.append(record)
    doc.details = DetailsPool(tuple(kept))
    by_number = {int(e.attrs['entnum']):e for e in doc.entries.of_tag('entry')}
    places = _Placements()
    for gf in doc.details.of_tag('gfhold'):
        if 'part' in gf.attrs:
            continue
        staff, measure = int(gf.attrs['cmper1']), int(gf.attrs['cmper2'])
        if measure not in keys:
            raise MalformedScoreError('Active frame has no score measure')
        for layer in range(1,5):
            frame = gf.fields.get(f'frame{layer}')
            if frame in (None,'','0'):
                continue
            _place_frame_entries(doc,int(frame),staff,measure,layer,keys[measure],by_number,places)
    if not places.by_entry:
        raise MalformedScoreError('No musical entries placed in score')
    doc.entries = EntriesPool(tuple(e for e in doc.entries.records
                                    if int(e.attrs['entnum']) in places.by_entry))
    return doc


def _documents(path):
    from finale_file_parser.enigma import mus_document as decoder, mus_rows, mus_others, mus_details
    from finale_file_parser.enigma.document import (
        EnigmaDocument, Pool, OptionsPool, OthersPool, DetailsPool, EntriesPool, TextsPool,
    )
    pools, kind = _pools(path)
    entries = _entries(pools)
    fallback = decoder._FALLBACK_ENCODING.get(decoder._banner_platform(path) or '', 'cp1252')
    texts = TextsPool(_texts(pools, fallback))
    if kind == 'zlib-records':
        others = mus_others.read_mus_others(path)
        raw_details = mus_details.read_mus_details(path)
        options = decoder._options_records(others, decoder._banner_year(path))
        # Older zlib banners use the same 18-byte clef definitions. Accept an
        # unambiguous known width, rather than dropping all their clefs.
        if not options:
            table = next((r for r in others if r.tag == mus_others.TAG_CLEF_OPTIONS
                          and r.cmper == mus_others.OPTIONS_CMPER), None)
            if table and table.payload:
                widths = [w for w in (18,20) if len(table.payload)%w == 0]
                if len(widths) == 1:
                    options = decoder._options_records(others, 2011 if widths[0] == 18 else 2012)
        translated = [r for r in decoder._details_records(raw_details) if r.tag != 'gfhold']
        for raw in raw_details:
            if raw.tag == mus_details.TAG_GFHOLD:
                translated.append(_gfhold(raw,'little','extended'))
        yield _normalise(EnigmaDocument('mus',Pool(()),Pool(()),OptionsPool(tuple(options)),
            OthersPool(tuple(decoder._others_records(others,fallback))),DetailsPool(tuple(translated)),
            EntriesPool(entries),texts)), kind, 'extended'
        return
    labelled = {p.kind:p for p in pools}
    if set(labelled) != {15,16,17,18}:
        raise MusStructureError('Unexpected labelled MUS pools')
    order = labelled[15].byte_order
    rows = mus_rows.MusRows(
        others={(r.tag,r.cmper):r for r in mus_rows._walk(labelled[15].data,order,4,'others')},
        details={(r.tag,r.cmper,r.cmper2):r for r in mus_rows._walk(labelled[16].data,order,6,'details')},
        byte_order=order)
    frames = {}
    for (tag,key), raw in rows.others.items():
        if tag == 'FR':
            span = decoder._frame_span(raw.payload,raw.incidences,order)
            if span is not None:
                frames[key] = span
    holds = [r for r in rows.details.values() if r.tag == 'GF']
    # The ten-byte, pre-layer format has a different record model. Decoding a
    # few surviving familiar records can produce a deceptively valid fragment;
    # it is unsupported until the complete model has an independent oracle.
    if not holds or any(len(r.payload) != 20 for r in holds):
        raise MusStructureError('Unverified pre-layer MUS record model')
    layouts = ['etf','extended']
    failures = []
    for layout in layouts:
        try:
            doc = EnigmaDocument('mus',Pool(()),Pool(()),
                OptionsPool(tuple(decoder._rows_options(rows))),
                OthersPool(tuple(decoder._rows_others(rows,frames))),
                DetailsPool(tuple(_gfhold(r,order,layout) for r in holds)),EntriesPool(entries),texts)
            yield _normalise(doc), kind, layout
        except (ValueError,KeyError,FinaleFileError) as error:
            failures.append(str(error))
    if failures and len(failures)==len(layouts):
        raise MusStructureError('No valid MUS row layout: '+'; '.join(failures))


def read_score(path):
    from finale_file_parser.enigma.to_ir import build_score
    scores = []
    failures = []
    try:
        for document, kind, layout in _documents(path):
            try:
                score = build_score(document)
                if score.parts:
                    scores.append(score)
            except (ValueError,KeyError,FinaleFileError) as error:
                failures.append(str(error))
    except (ValueError,KeyError,FinaleFileError) as error:
        failures.append(str(error))
    if not scores:
        raise MusStructureError('MUS structure could not be resolved: '+'; '.join(failures))
    if any(score != scores[0] for score in scores[1:]):
        raise MusStructureError('Ambiguous MUS row layouts; refusing to guess')
    return scores[0]

