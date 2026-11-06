from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import bootstrap
from mus_compat import read_score, MusStructureError, _inflate_zlib
from conversion import convert, score_xml
from finale_file_parser.errors import FinaleFileError
from finale_file_parser.export.musicxml import to_musicxml
from fixtures import fixture, modern_fixture, named_fixture


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def assert_notes(self,data):
        source=self.root/'test.mus';source.write_bytes(data)
        before=hashlib.sha256(data).digest()
        score=read_score(source)
        xml=ET.fromstring(to_musicxml(score))
        notes=xml.findall('.//note[pitch]')
        self.assertEqual(len(score.parts),1)
        self.assertEqual(len(notes),4)
        self.assertEqual([n.findtext('pitch/step') for n in notes],['C','D','E','F'])
        self.assertEqual({n.findtext('voice') for n in notes},{'1','2','3','4'})
        self.assertGreaterEqual(len(xml.findall('.//rest')),1)
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),before)
        return score

    def test_raw_layouts_and_byte_orders(self):
        for order in ['big','little']:
            for layout in ['etf','extended']:
                with self.subTest(order=order,layout=layout):
                    self.assert_notes(fixture(order,layout))

    def test_malformed_active_music_and_unknown_models_are_rejected(self):
        source=self.root/'bad.mus'
        for order in ['big','little']:
            for layout in ['etf','extended']:
                for kind in ['missing','truncated','unverified']:
                    with self.subTest(order=order,layout=layout,kind=kind):
                        source.write_bytes(fixture(order,layout,kind))
                        with self.assertRaises((MusStructureError,FinaleFileError)):
                            read_score(source)

    def test_compression_levels_and_banner_years(self):
        expected=self.assert_notes(modern_fixture())
        for year in [2000,2003,2006,2009,2011,2012]:
            for level in [0,1,6,9]:
                with self.subTest(year=year,level=level):
                    self.assertEqual(self.assert_notes(modern_fixture(year,level)).parts,expected.parts)

    def test_real_public_musx_in_isolated_worker(self):
        source=ROOT/'tests/fixtures/triplet.musx'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         'ab951d13a51461e67e8908c4dd603bb62aa64d1a18ce5f5856c8636f4c1d043b')
        target=self.root/'triplet.mxl'
        result=convert(source,target)
        self.assertEqual(result['status'],'success',result)
        self.assertEqual((result['parts'],result['measures'],result['notes']),(1,1,4))
        self.assertEqual(ET.fromstring(score_xml(target)).tag,'score-partwise')

    def test_large_pools_keep_all_four_layers(self):
        expected=self.assert_notes(modern_fixture())
        for pool in range(4):
            for level in [0,1,6,9]:
                with self.subTest(pool=pool,level=level):
                    self.assertEqual(self.assert_notes(modern_fixture(level=level,large_pool=pool)).parts,
                                     expected.parts)

    def test_inflation_extent_eof_and_budget(self):
        for size in [(1<<20)-1,1<<20,(1<<20)+1,(2<<20)+1]:
            data=b'a'*size
            stream=zlib.compress(data)
            trailing=zlib.compress(b'next pool')+b'metadata'
            with self.subTest(size=size):
                self.assertEqual(_inflate_zlib(stream+trailing,size),(data,len(stream)))
                with self.assertRaises(MusStructureError):
                    _inflate_zlib(stream,size-1)
                for cut in [1,4,8]:
                    with self.assertRaises(MusStructureError):
                        _inflate_zlib(stream[:-cut],size)

    def test_incomplete_last_pool_is_rejected(self):
        source=self.root/'truncated.mus'
        source.write_bytes(modern_fixture(large_pool=0)[:-2])
        with self.assertRaises(MusStructureError):read_score(source)

    def test_names_follow_references_and_group_names(self):
        source=self.root/'names.mus'
        for order in ['big','little']:
            for layout in ['etf','extended']:
                for case in ['individual','shared','missing','dangling','ambiguous']:
                    with self.subTest(order=order,layout=layout,case=case):
                        source.write_bytes(named_fixture(order,layout,case))
                        before=source.read_bytes()
                        score=read_score(source)
                        self.assertEqual([p.id for p in score.parts],['P2','P1'])
                        names={p.id:p.name for p in score.parts}
                        if case=='individual':self.assertEqual(names,{'P1':'Alpha \u266d','P2':'Beta'})
                        elif case=='shared':self.assertEqual(set(names.values()),{'Shared instrument'})
                        else:self.assertEqual(names,{'P1':'Staff 1','P2':'Staff 2'})
                        if case not in {'missing','dangling'}:
                            self.assertEqual(score.groups[0].name,'Shared instrument')
                            self.assertEqual(score.groups[0].abbreviation,'Shared')
                        xml=ET.fromstring(to_musicxml(score))
                        self.assertEqual(len(xml.findall('.//note[pitch]')),4)
                        self.assertNotIn('Unused palette name',names.values())
                        self.assertEqual(source.read_bytes(),before)


if __name__=='__main__':unittest.main()
