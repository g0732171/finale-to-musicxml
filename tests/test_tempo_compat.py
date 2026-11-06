"""Generated expression records: display text is independent of playback rate."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import bootstrap
from lxml import etree as ET
import musx2mxl.converter as converter
from finale_compat import install


class TempoCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals={name:getattr(converter,name) for name in
                       ['lookup_meas_expressions','translate_tempo_marks','process_gfholds']}
        # Exercise the real lookup inside the current-staff context without a UI.
        def process(staff,number,staff_number,measure,root,*args,**kwargs):
            expressions=converter.lookup_meas_expressions(root,number)
            for row in expressions:
                words,beat,dot,rate,parentheses=converter.translate_tempo_marks(row['text'])
                direction=ET.SubElement(measure,'direction')
                if words:ET.SubElement(ET.SubElement(direction,'direction-type'),'words').text=words
                if beat and rate:
                    mark=ET.SubElement(ET.SubElement(direction,'direction-type'),'metronome')
                    ET.SubElement(mark,'beat-unit').text=beat
                    ET.SubElement(mark,'per-minute').text=rate
            return expressions
        converter.process_gfholds=process
        install();install()

    @classmethod
    def tearDownClass(cls):
        for name,value in cls.originals.items():setattr(converter,name,value)
        del converter._finale_tempo_fixed

    def expressions(self,text,assignments=None,duration='1024',playback='65',staff='1'):
        ns=converter.ns['f']
        def element(parent,tag,text=None,**attrs):
            node=ET.SubElement(parent,'{'+ns+'}'+tag,**attrs);node.text=text;return node
        root=ET.Element('{'+ns+'}finale');others=element(root,'others');texts=element(root,'texts')
        category=element(others,'markingsCategory',cmper='1');element(category,'categoryType','tempoMarks')
        definition=element(others,'textExprDef',cmper='1')
        for tag,value in [('textIDKey','10'),('categoryID','1'),('playType','time'),
                          ('auxdata1',duration),('value',playback)]:element(definition,tag,value)
        element(definition,'useAuxData')
        block=element(others,'textBlock',cmper='10')
        element(block,'textID','50');element(block,'textTag','expression')
        element(texts,'expression',text,number='50')
        for assigned,offset,visibility in assignments or [('-1','0','scoreOnly')]:
            assignment=element(others,'measExprAssign',cmper='1')
            for tag,value in [('textExprID','1'),('staffAssign',assigned),('horzEduOff',offset),
                              ('showStaffList',visibility)]:element(assignment,tag,value)
        self.measure=ET.Element('measure')
        return converter.process_gfholds(staff,'1',1,self.measure,root,None)

    def translated(self,text,**kwargs):
        rows=self.expressions(text,**kwargs);self.assertEqual(len(rows),1)
        return converter.translate_tempo_marks(rows[0]['text'])

    def test_words_only_are_not_changed_to_metronome_marks(self):
        self.assertEqual(self.translated('Allegro'),('Allegro',None,False,None,None))

    def test_display_rate_is_not_overwritten_by_playback(self):
        self.assertEqual(self.translated('q = 80')[3],'80')
        self.assertEqual(self.translated('% = 80')[3],'80')

    def test_original_unknown_music_font_glyph_is_still_fixed(self):
        self.assertEqual(self.translated('% =65'),(None,'quarter',False,'65','no'))
        self.assertEqual(self.translated('Allegro (% =65)'),('Allegro','quarter',False,'65','yes'))

    def test_ranges_and_optional_bad_playback_metadata_keep_text(self):
        for text in ['% = 60\u201372','% = 60-72','% = 60 ~ 72']:
            with self.subTest(text=text):
                self.assertEqual(self.translated(text)[0],text)
                self.assertIsNone(self.translated(text)[1])
        self.assertEqual(self.translated('% =65',duration='not-a-number')[0],'% =65')

    def test_deduplication_only_removes_same_position(self):
        rows=self.expressions('% =65',assignments=[('-1','0','scoreOnly'),('-1','1024','partOnly')])
        self.assertEqual([r['horzEduOff'] for r in rows],['0','1024'])
        self.assertEqual(len(self.expressions('% =65',assignments=[('-1','0','scoreOnly'),('-1','0','partOnly')])),1)
        self.assertEqual(len(self.expressions('% =65',assignments=[('1','0','scoreOnly'),('2','0','scoreOnly')],staff='1')),1)

    def test_playback_and_display_remain_independent(self):
        self.expressions('q = 80',playback='65')
        self.assertEqual(self.measure.findtext('direction/direction-type/metronome/per-minute'),'80')
        self.assertEqual(self.measure.find('direction/sound').attrib['tempo'],'65')
        self.expressions('Allegro',playback='65')
        self.assertIsNone(self.measure.find('direction/direction-type/metronome'))
        self.assertEqual(self.measure.findtext('direction/direction-type/words'),'Allegro')
        self.assertEqual(self.measure.find('direction/sound').attrib['tempo'],'65')
        self.expressions('% = 80',duration='1536',playback='65')
        self.assertEqual(self.measure.find('direction/sound').attrib['tempo'],'97.5')
        self.expressions('% = 80',playback='invalid')
        self.assertIsNone(self.measure.find('direction/sound'))


if __name__=='__main__':unittest.main()
