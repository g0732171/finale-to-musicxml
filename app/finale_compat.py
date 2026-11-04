"""Compatibility fixes for musx2mxl 0.2.9; keep Finale tempo semantics."""
import re
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
            raise ValueError('Unexpected upstream expression mapping')
        global_ids = {a.findtext('f:textExprID', namespaces=namespace)
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
            if visibility == 'partOnly' and expression_id in global_ids:
                continue
            assigned = expression['staffAssign']
            if assigned != '-1' and str(assigned) != str(staff):
                continue
            if assigned == '-1' and staff_number not in (None, 1):
                continue
            key = (expression_id, expression['horzEduOff'])
            if key in seen:
                continue
            seen.add(key)
            # Finale stores the beat duration independently of the music font.
            if definition.findtext('f:playType', namespaces=namespace) == 'time':
                duration = definition.findtext('f:auxdata1', namespaces=namespace)
                value = definition.findtext('f:value', namespaces=namespace)
                if duration and value and definition.find('f:useAuxData', namespace) is not None:
                    beat, dots = calculate_type_and_dots(int(duration))
                    if beat and dots <= 1 and float(value) > 0:
                        plain = remove_styling_tags(expression['text'])
                        # Replace only the metronome equation; retain surrounding words.
                        words = re.sub(r'[^\s=()]+\s*=\s*(?:c[.a]*\s*)?\d+(?:\.\d+)?', '', plain).strip()
                        parentheses = 'yes' if words == '()' else 'no'
                        if parentheses == 'yes':
                            words = ''
                        text = TempoText(expression['text'])
                        text.tempo = (words or None, beat, bool(dots), value, parentheses)
                        expression = dict(expression, text=text)
            result.append(expression)
        return result

    def translate(text):
        return text.tempo if isinstance(text, TempoText) else original_translate(text)

    @wraps(original_process)
    def process(staff, number, staff_number, measure, *args, **kwargs):
        token = current_staff.set((staff, staff_number))
        old_children = set(measure)
        try:
            result = original_process(staff, number, staff_number, measure, *args, **kwargs)
            for direction in measure.findall('direction'):
                if direction in old_children:
                    continue
                metronome = direction.find('direction-type/metronome')
                if metronome is None:
                    continue
                if staff_number is not None:
                    SubElement(direction, 'staff').text = str(staff_number)
                unit = metronome.findtext('beat-unit')
                quarters = {'whole': 4, 'half': 2, 'quarter': 1, 'eighth': .5,
                            '16th': .25, '32nd': .125, '64th': .0625}.get(unit)
                try:
                    rate = float(metronome.findtext('per-minute'))
                except (ValueError, TypeError):
                    continue
                if quarters:
                    tempo = rate * quarters * (1.5 if metronome.find('beat-unit-dot') is not None else 1)
                    SubElement(direction, 'sound', tempo=format(tempo, 'g'))
            return result
        finally:
            current_staff.reset(token)

    converter.lookup_meas_expressions = lookup
    converter.translate_tempo_marks = translate
    converter.process_gfholds = process
