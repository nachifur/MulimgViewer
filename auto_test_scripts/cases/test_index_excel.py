"""Validate XLSX content, view schemas, splitting and atomic cancellation."""
import sys
import zipfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import CancelledError
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.index_excel import write_index_xlsx
from mulimgviewer.src.index_columns import view_columns, export_filename, view_row
import test_browsing_index as index_fixtures

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def sheets(path):
    with zipfile.ZipFile(path) as archive:
        workbook=ET.fromstring(archive.read('xl/workbook.xml'))
        result={}
        for number,sheet in enumerate(workbook.find('m:sheets',NS),1):
            root=ET.fromstring(archive.read(f'xl/worksheets/sheet{number}.xml'))
            rows=[]
            for row in root.findall('m:sheetData/m:row',NS):
                values=[]
                for cell in row:
                    if cell.get('t')=='inlineStr':values.append(''.join(cell.find('m:is',NS).itertext()))
                    else:
                        value=cell.find('m:v',NS)
                        values.append(value.text if value is not None else '')
                rows.append(values)
            result[sheet.get('name')]=(rows,root)
        return result


class ExcelIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def test_all_views_have_distinct_names_and_matching_excel_columns(self):
        names=set()
        for video in (False,True):
            model=index_fixtures.TimelineTests().model(video=video)
            for view in (0,1,2):
                name=export_filename(view,video);names.add(name)
                path=self.root/name
                total=write_index_xlsx(path,model,view)
                data=sheets(path)[('Sources','Pages','Visual items')[view]+' 1']
                self.assertEqual(data[0][0],[column.label for column in view_columns(view,video)])
                self.assertEqual(len(data[0])-1,total)
                self.assertIsNotNone(data[1].find('m:autoFilter',NS))
                pane=data[1].find('m:sheetViews/m:sheetView/m:pane',NS)
                self.assertEqual(pane.get('state'),'frozen')
                self.assertTrue(all(len(row)==len(data[0][0]) for row in data[0][1:]))
        self.assertEqual(len(names),6)

    def test_algorithm_columns_export_the_processed_path_and_plugin_entry(self):
        import json
        from mulimgviewer.src.index_catalog import IndexCatalog
        layout=[None]*41
        layout[0]=[1,2];layout[1]=[1,1];layout[22]=False
        layout[24]=layout[25]=False;layout[32]=True;layout[36]=True;layout[37]=0
        layout[38]=False;layout[39]='5,1';layout[40]=False
        registry=(('Example','/plugins/Example/main.py','',json.dumps({'identity':False})),
                  ('Original','/plugins/Original/main.py','',json.dumps({'identity':True,'role':'original'})))
        manager=SimpleNamespace(type=1,parallel_to_sequential=False,count_per_action=1,
            path_list=['a','b'],name_list=['input.png'],layout_params=layout,_custom_algorithm_registry=registry)
        cfg=SimpleNamespace(video_mode=False,parallel_to_sequential=False,skip_frames=0,
            video_fps_list=[],video_num_list=[],real_video_path=[])
        model=IndexCatalog(manager,cfg)
        output=self.root/'algorithms.xlsx';write_index_xlsx(output,model,2)
        records,xml=sheets(output)['Visual items 1']
        for index in range(model.visual_total):
            entry=model.visual_entry(index);record=records[index+1]
            for label,value in (('Algorithm',entry['algorithm']),('Algorithm path',entry['algorithm_path']),
                                ('Image / cache path',entry['path'])):
                self.assertEqual(record[records[0].index(label)],value)

    def test_pages_split_at_excel_row_limit_without_losing_rows(self):
        model=index_fixtures.TimelineTests().model();path=self.root/'pages.xlsx'
        write_index_xlsx(path,model,1,sheet_rows=4)
        data=sheets(path)
        pages=[rows for name,(rows,root) in data.items() if name.startswith('Pages ')]
        self.assertEqual([len(rows)-1 for rows in pages],[3,3,3,3,1])
        self.assertEqual([row[0] for rows in pages for row in rows[1:]],[str(i) for i in range(1,14)])

    def test_cancellation_preserves_existing_file_and_cleans_temporary_work(self):
        model=index_fixtures.TimelineTests().model();path=self.root/'keep.xlsx';path.write_bytes(b'original')
        calls=[]
        def canceled():calls.append(1);return len(calls)>3
        with self.assertRaises(CancelledError):write_index_xlsx(path,model,2,canceled)
        self.assertEqual(path.read_bytes(),b'original')
        self.assertFalse(list(self.root.glob('.index_excel_*')))

    def test_long_paths_and_unicode_are_preserved_in_continuation_sheet(self):
        text='a/'+'video-path-'*5000
        model=SimpleNamespace(video=False,order='parallel',rows=lambda view:1,
                              page_row=lambda index:('1','1','Folder 1','1',text))
        path=self.root/'long.xlsx'
        write_index_xlsx(path,model,1)
        data=sheets(path)
        chunks=[row[4] for name,(rows,root) in data.items() if name.startswith('Long text') for row in rows[1:]]
        self.assertEqual(''.join(chunks),text)
        self.assertIn('Full text',data['Pages 1'][0][1][-1])

    def test_text_is_not_converted_to_excel_formula_and_ids_are_numeric(self):
        model=SimpleNamespace(video=False,order='parallel',rows=lambda view:1,
                              source_row=lambda index:('1','1','Folder 1','Image 1','=1+2'))
        path=self.root/'text.xlsx';write_index_xlsx(path,model,0)
        rows,root=sheets(path)['Sources 1']
        self.assertEqual(rows[1][-1],'=1+2')
        self.assertIsNone(root.find('.//m:f',NS))
        cell=root.find('m:sheetData/m:row[@r="2"]/m:c',NS)
        self.assertNotEqual(cell.get('t'),'inlineStr')

    def test_cache_snapshot_distinguishes_unknown_virtual_and_cached(self):
        model=index_fixtures.TimelineTests().model();path=self.root/'states.xlsx'
        first=model.visual_entry(0)['path'];second=model.visual_entry(1)['path']
        write_index_xlsx(path,model,2,cache_states={first:True,second:False})
        rows,root=sheets(path)['Visual items 1']
        self.assertEqual(rows[1][-1],'Cached')
        self.assertEqual(rows[2][-1],'Virtual / not cached')
        self.assertEqual(rows[3][-1],'Not checked')

if __name__=='__main__':unittest.main()
