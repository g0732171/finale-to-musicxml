"""Compatibility fixes for musx2mxl 0.2.9; keep Finale tempo semantics."""
import re
import math
from contextvars import ContextVar
from functools import wraps


class TempoText(str):
    pass


def install():
    from lxml.etree import SubElement
    import musx2mxl.converter as converter
    from musx2mxl.helper import calculate_type_and_dots, remove_styling_tags

    if getattr(converter, '_finale_tempo_fixed', False):
        return
    converter._finale_tempo_fixed = True
    namespace = converter.ns
    current_staff = ContextVar('finale_staff', default=(None, None))
    current_directions = ContextVar('finale_tempo_directions',default=None)
    original_lookup = converter.lookup_meas_expressions
    original_translate = converter.translate_tempo_marks
    original_process = converter.process_gfholds

    def lookup(root, measure_number):
        expressions = original_lookup(root, measure_number)
        assignments = root.xpath(
            "/f:finale/f:others/f:measExprAssign[@cmper=$number][f:textExprID]",
            namespaces=namespace, number=str(measure_number))
        # Upstream returns one expression per resolved text assignment.
        resolved = []
        for assignment in assignments:
            definition = root.find('f:others/f:textExprDef[@cmper="%s"]' %
                                   assignment.findtext('f:textExprID', namespaces=namespace), namespace)
            block = root.find('f:others/f:textBlock[@cmper="%s"]' %
                             definition.findtext('f:textIDKey', namespaces=namespace), namespace)
            if block is not None:
                text = root.find('f:texts/f:expression[@number="%s"]' %
                                 block.findtext('f:textID', namespaces=namespace), namespace)
                if text is not None and text.text:
                    resolved.append((assignment, definition))
        if len(resolved) != len(expressions):
            # A cosmetic fix must not make a score unreadable if an upstream
            # lookup changes. Keep its original expressions in that case.
            return expressions
        def position(assignment):
            return assignment.findtext('f:horzEduOff',default='0',namespaces=namespace) or '0'
        global_ids = {(a.findtext('f:textExprID', namespaces=namespace),position(a))
                      for a, _ in resolved
                      if a.findtext('f:showStaffList', namespaces=namespace) == 'scoreOnly'
                      and a.findtext('f:staffAssign', namespaces=namespace) == '-1'}
        staff, staff_number = current_staff.get()
        seen = set()
        result = []
        for expression, (assignment, definition) in zip(expressions, resolved):
            if expression['categoryType'] != 'tempoMarks':
                result.append(expression)
                continue
            expression_id = assignment.findtext('f:textExprID', namespaces=namespace)
            visibility = assignment.findtext('f:showStaffList', namespaces=namespace)
            if visibility == 'partOnly' and (expression_id,position(assignment)) in global_ids:
                continue
            assigned = expression['staffAssign']
            if assigned != '-1' and str(assigned) != str(staff):
                continue
            if assigned == '-1' and staff_number not in (None, 1):
                continue
            key = (expression_id, position(assignment))
            if key in seen:
                continue
            seen.add(key)
            text = TempoText(expression['text'])
            text.playback = None
            if (definition.findtext('f:playType',namespaces=namespace) == 'time' and
                    definition.find('f:useAuxData',namespace) is not None):
                try:
                    playback = float(definition.findtext('f:value',namespaces=namespace))
                    duration = int(definition.findtext('f:auxdata1',namespaces=namespace))
                    quarters = playback*duration/1024
                    if playback > 0 and duration > 0 and math.isfinite(quarters):
                        text.playback = quarters
                except (ValueError,TypeError,OverflowError):
                    pass
            expression = dict(expression,text=text)
            # Finale stores the beat duration independently of the music font.
            if definition.findtext('f:playType', namespaces=namespace) == 'time':
                duration = definition.findtext('f:auxdata1', namespaces=namespace)
                plain = remove_styling_tags(expression['text'])
                equation = re.search(r'(?P<glyph>[^\s=()]+)\s*=\s*(?P<approx>c[.a]*\s*)?(?P<rate>\d+(?:\.\d+)?)',plain)
                # Playback settings do not prescribe visible notation. Only
                # repair a simple equation with an unrecognised single glyph.
                if duration and equation and definition.find('f:useAuxData',namespace) is not None:
                    glyph = equation.group('glyph')
                    before,after = plain[:equation.start()],plain[equation.end():]
                    complex_tail = after.lstrip().startswith(tuple('0123456789-\u2013\u2014~\u301c/=.\u2192,'))
                    recognised = re.fullmatch(r'[xeqh][d.]?',glyph) is not None
                    if complex_tail or '=' in before+after:
                        text.tempo = (plain,None,False,None,None)
                        result.append(expression)
                        continue
                    try:
                        beat,dots = calculate_type_and_dots(int(duration))
                        rate = float(equation.group('rate'))
                    except (ValueError,TypeError,OverflowError):
                        beat,dots,rate = None,0,0
                    if (len(glyph) == 1 and not recognised and not complex_tail and
                            '=' not in before+after and beat and dots <= 1 and
                            math.isfinite(rate) and rate > 0):
                        parentheses = 'yes' if before.rstrip().endswith('(') and after.lstrip().startswith(')') else 'no'
                        if parentheses == 'yes':
                            before = before.rstrip()[:-1]
                            after = after.lstrip()[1:]
                        words = ' '.join(s for s in [before.strip(),after.strip()] if s)
                        printed_rate = (equation.group('approx') or '')+equation.group('rate')
                        text.tempo = (words or None,beat,bool(dots),printed_rate,parentheses)
            result.append(expression)
        return result

    def translate(text):
        if isinstance(text,TempoText):
            context = current_directions.get()
            if context is not None:
                # Pinned upstream calls this immediately before appending the
                # corresponding direction. Capture that boundary, not a guess
                # based on other markings' category or order.
                context['items'].append((set(context['measure'].findall('direction')),text.playback))
            if hasattr(text,'tempo'):
                return text.tempo
        return original_translate(text)

    @wraps(original_process)
    def process(staff, number, staff_number, measure, *args, **kwargs):
        token = current_staff.set((staff, staff_number))
        context = {'measure':measure,'items':[]}
        direction_token = current_directions.set(context)
        try:
            result = original_process(staff, number, staff_number, measure, *args, **kwargs)
            for previous,playback in context['items']:
                direction = next((d for d in measure.findall('direction') if d not in previous),None)
                if direction is None:
                    continue
                if staff_number is not None and direction.find('staff') is None:
                    SubElement(direction, 'staff').text = str(staff_number)
                if playback is not None:
                    SubElement(direction,'sound',tempo=format(playback,'g'))
            return result
        finally:
            current_staff.reset(token)
            current_directions.reset(direction_token)

    converter.lookup_meas_expressions = lookup
    converter.translate_tempo_marks = translate
    converter.process_gfholds = process
