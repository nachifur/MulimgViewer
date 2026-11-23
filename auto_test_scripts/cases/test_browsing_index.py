"""Continuous video timelines and lazy image/video index regressions."""
import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from mulimgviewer.src.video_source import page_count,page_segments,raw_dependencies
from mulimgviewer.src.index_table import IndexCatalog


class AutoLayoutAdviceTests(unittest.TestCase):
    def test_image_layout_is_positive_bounded_and_keeps_existing_small_shapes(self):
        from mulimgviewer.src.data import ImgData
        for count,expected in ((0,[1,1]),(1,[1,1]),(2,[1,2]),(3,[2,2]),
                (5,[2,3]),(24,[4,6]),(303,[3,50]),(10**12,[50,50])):
            with self.subTest(count=count):
                self.assertEqual(ImgData.layout_advice(SimpleNamespace(type=2,img_num=count)),expected)
        self.assertEqual(ImgData.layout_advice(SimpleNamespace()),[1,1])

    def test_long_videos_use_source_count_without_iterating_virtual_frames(self):
        from mulimgviewer.src.data import ImgData
        class NoFrames:
            def __iter__(self):raise AssertionError('Automatic layout must not enumerate video frames')
        for count,expected in ((1,[1,1]),(24,[4,6])):
            for serial in (False,True):
                manager=SimpleNamespace(type=1,video_mode=True,path_list=list(range(count)),
                    parallel_to_sequential=serial,img_num=10**12,name_list=NoFrames())
                self.assertEqual(ImgData.layout_advice(manager),expected)

    def test_empty_parallel_sources_and_csv_shapes_do_not_create_zero_dimensions_or_aliases(self):
        from mulimgviewer.src.data import ImgData
        manager=SimpleNamespace(type=1,parallel_to_sequential=True,name_list=[[],['a','b','c']])
        self.assertEqual(ImgData.layout_advice(manager),[2,2])
        manager=SimpleNamespace(csv_flag=True,csv_row_col=[2,3])
        shape=ImgData.layout_advice(manager);shape[0]=99
        self.assertEqual(manager.csv_row_col,[2,3])
        manager.csv_row_col=[0,0]
        self.assertEqual(ImgData.layout_advice(manager),[1,1])


class TimelineTests(unittest.TestCase):
    def test_serial_image_page_spans_empty_and_large_folders(self):
        from mulimgviewer.src.utils_img import ImgManager
        with tempfile.TemporaryDirectory() as folder:
            sources = [Path(folder)/str(i) for i in range(3)]
            for directory in sources:
                directory.mkdir()
            for i in range(101):
                (sources[0]/f'{i:03}.jpg').touch()
            (sources[2]/'last.png').touch()
            manager = ImgManager()
            manager.init(list(map(str, sources)), type=1, parallel_to_sequential=True)
            manager.set_count_per_action(4)
            manager.set_action_count(25)
            self.assertEqual(manager.img_num, 102)
            self.assertEqual(manager.get_flist(), [
                str(sources[0]/manager.name_list[0][-1]), str(sources[2]/'last.png')])

    def test_long_video_frame_names_and_cross_video_pages_are_lazy(self):
        from unittest.mock import patch
        from mulimgviewer.src.utils_img import ImgManager
        from mulimgviewer.src.video_source import FrameNames, frame_filename
        counts = [10**9+1, 10**9+2]
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory)/str(index) for index in (0,1)]
            for path in paths:path.mkdir()
            manager = ImgManager()
            manager.init([str(path) for path in paths], type=1, video_mode=True,
                         parallel_to_sequential=True, video_fps_list=[24.,30.], video_num_list=counts)
            manager.set_count_per_action(3)
            manager.set_action_count(counts[0]//3)
            with patch('mulimgviewer.src.video_source.frame_filename', wraps=frame_filename) as names:
                files = manager.get_flist()
                self.assertEqual(names.call_count, 3)
            expected = [str(paths[0]/frame_filename(counts[0]-2,24.)),
                        str(paths[0]/frame_filename(counts[0]-1,24.)),
                        str(paths[1]/frame_filename(0,30.))]
            self.assertEqual(files, expected)
            self.assertIsInstance(manager.name_list[0], FrameNames)
            self.assertEqual(len(manager.name_list[0]), counts[0])
            manager.parallel_to_sequential = False
            manager.set_action_count(1)
            files = manager.get_flist()
            self.assertEqual(files, [str(path/frame_filename(index,fps))
                                    for path,fps in zip(paths,(24.,30.)) for index in (3,4,5)])
            manager.init(str(paths[0]), type=2, video_mode=True,
                         video_fps_list=[0.], video_num_list=[10**9], skip=2)
            manager.set_count_per_action(1)
            manager.set_action_count(10**9-1)
            self.assertEqual(manager.get_flist(), [str(paths[0]/frame_filename(10**9-1,0.,3))])

    def test_all_serial_frames_appear_once_including_empty_and_short_videos(self):
        for counts in ([303,303,303],[1,0,2,1],[80,80],[0,0]):
            for size in (1,3,48,1000):
                frames=[(v,i) for batch in range(page_count(counts,size,True))
                        for v,a,b in page_segments(counts,size,batch,True) for i in range(a,b)]
                self.assertEqual(frames,[(v,i) for v,n in enumerate(counts) for i in range(n)])

    def test_boundary_dependencies_cover_both_local_raw_pages(self):
        self.assertEqual(page_segments([303,303],48,6,True),[(0,288,303),(1,0,33)])
        self.assertEqual(page_segments([303,303],48,7,True),[(1,33,81)])
        self.assertEqual(raw_dependencies([303,303],48,7,True),[(1,0),(1,1)])
        self.assertEqual(page_segments([3,8],3,2,False),[(0,0,3),(1,6,8)])

    def model(self, video=True, serial=True, kind=1, sequential=False):
        cfg=SimpleNamespace(video_mode=video,parallel_to_sequential=serial,
            real_video_path=['one.mp4','two.mp4'],video_num_list=[303,303],
            video_fps_list=[30.,30.],skip_frames=0)
        manager=SimpleNamespace(type=kind,parallel_to_sequential=serial,count_per_action=48,
            path_list=['a','b'],name_list=[['one.png'],['two.png']] if serial else ['one.png','two.png'])
        return IndexCatalog(manager,cfg,sequential)

    def test_video_index_uses_exact_same_cross_video_spans(self):
        model=self.model()
        self.assertEqual(model.pages,13)
        self.assertIn('1-33',model.page_row(6)[3])
        self.assertEqual(model.source_row(1)[1],'7-13')
        self.assertEqual(model.target(0,1),6)
        self.assertEqual(model.search('page:7',0,lambda:False)[0],[0,1])
        self.assertEqual(model.search('two.mp4',1,lambda:False)[0],list(range(6,13)))

    def test_image_modes_and_both_layout_switches(self):
        for kind in (0,1,2,3):
            for serial in (False,True):
                model=self.model(False,serial,kind,True)
                if model.sources:
                    self.assertEqual(model.row(0,0)[0],'1')
                    self.assertGreaterEqual(model.pages,1)
                    self.assertEqual(model.target(0,0),0)
                    self.assertTrue(model.row(1,0)[4])

    def test_visual_order_interleaves_nested_rows_and_virtual_paths(self):
        from mulimgviewer.src.index_table import visual_cells
        order=list(visual_cells((1,2),(2,2)))
        self.assertEqual([slot for y,x,slot in order],[0,1,4,5,2,3,6,7])
        model=self.model()
        self.assertEqual(model.visual_entry(0)['id'],1)
        entry=model.visual_entry(303)
        self.assertEqual(entry['video'],1)
        self.assertEqual(entry['frame'],0)
        self.assertTrue(entry['path'].endswith('0s_frame_1.jpeg'))
        self.assertEqual(model.target(2,303),6)
        matches,limited=model.search(entry['path'],2,lambda:False)
        self.assertIn(303,matches)
        self.assertFalse(limited)
        self.assertEqual(model.search('id:304',2,lambda:False),([303],False))
        self.assertEqual(model.search('',2,lambda:False),([],False))

    def test_visual_ids_dense_for_short_parallel_streams_and_layouts(self):
        from itertools import product
        for kind in (0,1,2,3):
            for serial,vertical0,vertical1 in product((False,True),repeat=3):
                cfg=SimpleNamespace(video_mode=False,parallel_to_sequential=serial,real_video_path=[],
                    video_num_list=[],video_fps_list=[],skip_frames=0)
                names=[['1.png','2.png','3.png'],['a.png','b.png']] if serial else ['1.png','2.png','3.png']
                paths=['a','b'] if kind!=3 else ['a/1.png','b/2.png','a/3.png']
                if kind==2:paths=['a'];names=[names[0]] if serial else names
                layout=[[2,2],[2,2]]+[None]*22+[vertical0,vertical1]
                manager=SimpleNamespace(type=kind,parallel_to_sequential=serial,path_list=paths,
                    name_list=names,count_per_action=2,layout_params=layout)
                model=IndexCatalog(manager,cfg,True)
                entries=[model.visual_entry(i) for i in range(model.visual_total)]
                self.assertEqual([e['id'] for e in entries],list(range(1,len(entries)+1)))
                coords=[(e['page'],e['row'],e['column']) for e in entries]
                self.assertEqual(coords,sorted(coords))

    def test_billion_frame_future_path_lookup_does_not_scan_frames(self):
        cfg=SimpleNamespace(video_mode=True,parallel_to_sequential=True,
            real_video_path=['one.mp4','two.mp4'],video_num_list=[10**9,10**9],
            video_fps_list=[30.,30.],skip_frames=0,video_path=['cache/a','cache/b'])
        manager=SimpleNamespace(type=1,parallel_to_sequential=True,count_per_action=48,
                                path_list=cfg.video_path,name_list=[])
        model=IndexCatalog(manager,cfg)
        self.assertEqual(model.visual_total,2*10**9)
        entry=model.visual_entry(10**9+301)
        calls=[]
        def stopped():
            calls.append(1)
            if len(calls)>100:raise AssertionError('Scanned virtual frames instead of locating filename')
            return False
        matches,limited=model.search(entry['path'],2,stopped)
        self.assertIn(10**9+301,matches)
        self.assertFalse(limited)
        self.assertLess(len(calls),100)
        self.assertLessEqual(model._visual_page.cache_info().currsize,2)

    def test_video_visual_mapping_independent_of_input_mode_tag(self):
        for kind in (0,1,2,3):
            for serial in (False,True):
                cfg=SimpleNamespace(video_mode=True,parallel_to_sequential=serial,
                    real_video_path=['one.mp4','two.mp4'],video_num_list=[303,301],
                    video_fps_list=[30.,30.],skip_frames=0,video_path=['cache/a','cache/b'])
                manager=SimpleNamespace(type=kind,parallel_to_sequential=serial,count_per_action=48,
                                        path_list=cfg.video_path,name_list=[])
                model=IndexCatalog(manager,cfg,not serial)
                self.assertEqual(model.pages,13 if serial else 7)
                self.assertEqual(model.visual_total,604)
                self.assertEqual(model.visual_entry(0)['frame'],0)
                self.assertEqual(model.visual_entry(model.visual_total-1)['frame'],300)

    def test_path_search_includes_repeated_short_video_frames(self):
        cfg=SimpleNamespace(video_mode=True,parallel_to_sequential=False,
            real_video_path=['one.mp4','two.mp4'],video_num_list=[1,4],
            video_fps_list=[30.,30.],skip_frames=0,video_path=['cache/a','cache/b'])
        manager=SimpleNamespace(type=1,parallel_to_sequential=False,count_per_action=2,
                                path_list=cfg.video_path,name_list=[])
        model=IndexCatalog(manager,cfg)
        path=model.visual_entry(0)['path']
        self.assertEqual(model.search(path,2,lambda:False),([0,3],False))

    def test_processed_future_frame_path_search_is_bounded_and_algorithm_specific(self):
        import json
        model=self.model()
        cfg=SimpleNamespace(video_mode=True,parallel_to_sequential=False,
            real_video_path=['one.mp4','two.mp4'],video_num_list=[10**9,10**9],
            video_fps_list=[30.,30.],skip_frames=0,video_path=['cache/a','cache/b'])
        layout=[None]*41;layout[0]=[1,2];layout[1]=[1,1];layout[22]=False
        layout[24]=layout[25]=False;layout[32]=True;layout[36]=True;layout[37]=0
        layout[38]=False;layout[39]='5,1';layout[40]=False
        registry=(('Example','/plugins/Example/main.py','',json.dumps({'identity':False})),
                  ('Original','/plugins/Original/main.py','',json.dumps({'identity':True,'role':'original'})))
        manager=SimpleNamespace(type=1,parallel_to_sequential=False,count_per_action=1,
            path_list=cfg.video_path,name_list=[],layout_params=layout,_custom_algorithm_registry=registry)
        model=IndexCatalog(manager,cfg)
        target=model.visual_page_start(900000000)+2
        entry=model.visual_entry(target)
        self.assertEqual(entry['algorithm'],'Example')
        self.assertEqual(entry['algorithm_path'],'/plugins/Example/main.py')
        self.assertEqual(Path(entry['path']).parent.parent.name,'frames')
        self.assertEqual(Path(entry['path']).parent.name,'one')
        self.assertTrue(entry['path'].endswith('.jpeg'))
        manager.cache_save_format=1
        png_model=IndexCatalog(manager,cfg)
        self.assertTrue(png_model.visual_entry(target)['path'].endswith('.png'))
        self.assertTrue(entry['path'].endswith('.jpeg'))  # Existing catalog keeps its snapshot.
        calls=[]
        def stop():
            calls.append(1)
            if len(calls)>100:raise AssertionError('Scanned virtual video frames')
            return False
        matches,limited=model.search(entry['path'],2,stop)
        self.assertIn(target,matches)
        self.assertFalse(limited)
        self.assertTrue(all(model.visual_entry(i)['algorithm']=='Example' for i in matches))
        self.assertLess(len(calls),100)

    def test_long_video_catalog_does_not_create_frame_rows(self):
        model=self.model()
        model.counts=(10**9,10**9)
        model.prefix=[0,10**9,2*10**9]
        model.pages=page_count(model.counts,48,True)
        self.assertEqual(model.sources,2)
        for i in range(200):model.row(1,i)
        self.assertLessEqual(len(model._row_cache),128)
        self.assertEqual(model.search('nothing',0,lambda:False),([],False))



class IndexWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx=wx
        cls.app=wx.App.Get() or wx.App(False)

    def setUp(self):
        from mulimgviewer.src.index_table import IndexTable
        self.temp=tempfile.TemporaryDirectory()
        self.jumps=[]
        self.catalog=TimelineTests().model()
        self.window=IndexTable(None,self.catalog,on_jump=self.jumps.append,show=False)
        self.window._choose_view(0);self.window.change_view(None)

    def tearDown(self):
        self.window.Close()
        self.window._workers.shutdown(wait=True)
        self.app.Yield(True)
        self.temp.cleanup()

    def pump(self, predicate):
        import time
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            self.app.Yield(True)
            if predicate():return
            time.sleep(.005)
        self.fail('Index worker did not finish')

    def test_virtual_video_search_no_match_and_jump(self):
        self.assertEqual(self.window.index_table.GetItemCount(),2)
        self.window.m_search_txt.ChangeValue('not-present')
        self.window.search_txt(None)
        self.pump(lambda:self.window.match_label.GetLabel()=='No matches')
        self.assertFalse(self.window.b_next_txt.IsEnabled())
        self.window.m_search_txt.ChangeValue('two.mp4')
        self.window.search_txt(None)
        self.pump(lambda:bool(self.window.id_list))
        self.assertEqual(self.window.id_list,[1])
        event=self.wx.ListEvent(self.wx.EVT_LIST_ITEM_ACTIVATED.typeId,self.window.index_table.GetId())
        event.SetIndex(1)
        self.window.activate_row(event)
        self.assertEqual(self.jumps,[6])
        self.window._choose_view(1)
        self.window.change_view(None)
        self.assertEqual(self.window.index_table.GetItemCount(),13)
        self.assertIn('1-33',self.window.index_table.GetItemText(6,2))

    def test_visual_frame_paths_change_cached_state_without_decoding(self):
        self.window._choose_view(2);self.window.change_view(None)
        self.window._select_index(0)
        path=Path(self.window._selected_entry['path'])
        # Replace the cache folder with this test's temporary directory.
        self.catalog.cache_paths=(self.temp.name,self.temp.name)
        self.catalog._row_cache.clear();self.catalog._visual_page.cache_clear()
        self.window._select_index(0)
        path=Path(self.window._selected_entry['path'])
        self.assertTrue(self.window.copy_frame_button.IsEnabled())
        self.window._probe_visible(None)
        self.pump(lambda:str(path) in self.window._cache_states)
        self.assertFalse(self.window._cache_states[str(path)])
        path.write_bytes(b'cached image placeholder')
        self.window._probe_visible(None)
        self.pump(lambda:self.window._cache_states.get(str(path)) is True)
        self.assertIn('Cached',self.window.path_details.GetValue())
        path.unlink()
        self.window._probe_visible(None)
        self.pump(lambda:self.window._cache_states.get(str(path)) is False)
        self.assertIn('Virtual',self.window.path_details.GetValue())

    def test_cache_probes_do_not_reset_selected_detail_text(self):
        from unittest.mock import patch
        self.window._probe_timer.Stop()
        self.window._choose_view(2);self.window.change_view(None)
        self.catalog.cache_paths=(self.temp.name,self.temp.name)
        self.catalog._row_cache.clear();self.catalog._visual_page.cache_clear()
        self.window._select_index(0)
        path=Path(self.window._selected_entry['path'])
        self.window._probe_visible(None)
        self.pump(lambda:str(path) in self.window._cache_states)
        details=self.window.path_details
        details.SetSelection(5,22)
        selected=details.GetStringSelection();selection=details.GetSelection()
        with patch.object(details,'ChangeValue',wraps=details.ChangeValue) as changed:
            self.window._probe_visible(None)
            self.pump(lambda:self.window._probe_future.done())
            self.app.Yield(True)
            self.assertEqual(details.GetSelection(),selection)
            self.assertEqual(details.GetStringSelection(),selected)
            changed.assert_not_called()
            path.write_bytes(b'cached image placeholder')
            self.window._probe_visible(None)
            self.pump(lambda:self.window._cache_states.get(str(path)) is True)
            self.assertEqual(details.GetSelection(),selection)
            self.assertEqual(details.GetStringSelection(),selected)
            self.assertEqual(self.window._display_row(0)[-1],'Cached')
            changed.assert_not_called()
        # Changing the selected row still updates details immediately.
        self.window._select_index(1)
        self.assertIn('ID 2 |',details.GetValue())

    def test_focused_detail_caret_survives_status_change_and_catches_up_after_reading(self):
        from unittest.mock import patch
        self.window._probe_timer.Stop()
        self.window._choose_view(2);self.window.change_view(None)
        self.window._select_index(0)
        details=self.window.path_details
        details.SetInsertionPoint(14)
        before=details.GetValue()
        self.window._cache_states[self.window._selected_entry['path']]=True
        with patch.object(details,'HasFocus',return_value=True):
            self.window._select_index(0,preserve_details=True)
        self.assertEqual(details.GetValue(),before)
        self.assertEqual(details.GetInsertionPoint(),14)
        with patch.object(details,'HasFocus',return_value=False):
            self.window._select_index(0,preserve_details=True)
        self.assertIn('Cached',details.GetValue())
        self.assertEqual(details.GetInsertionPoint(),14)

    def test_bidirectional_buttons_locate_visual_row_and_return_exact_rank(self):
        locations=[dict(page=6,rank=15)]
        jumps=[]
        self.window.on_locate=lambda:locations[-1]
        self.window.on_jump_item=lambda page,rank,context:jumps.append((page,rank))
        self.window.locate_main_image(None)
        self.assertEqual(self.window.view,2)
        self.assertEqual(self.window.index_table.GetFirstSelected(),303)
        self.assertEqual(self.window._selected_entry['video'],1)
        self.window.jump_selected(None)
        self.assertEqual(jumps,[(6,15)])
        locations.append(dict(page=7,rank=0))
        self.window.locate_main_image(None)
        self.assertEqual(self.window.index_table.GetFirstSelected(),336)

    def test_toolbar_uses_current_fbp_parent_without_fixed_container_name(self):
        panel=self.window.m_search_txt.GetParent()
        self.assertIsInstance(panel,self.wx.Panel)
        minimum=panel.GetMinSize()
        for width in (750,1150,1500):
            self.window.SetClientSize((width,650))
            self.window.Layout()
            self.window.resize_controls_row(None)
            self.app.Yield(True)
            self.assertEqual(panel.GetMinSize().width,minimum.width)
            row_height=panel.GetSizer().GetMinSize().height
            scrollbar=max(0,self.wx.SystemSettings.GetMetric(self.wx.SYS_HSCROLL_Y,panel))
            if isinstance(panel,self.wx.ScrolledWindow):
                self.assertGreaterEqual(panel.GetMinSize().height,row_height)
                self.assertLessEqual(panel.GetMinSize().height,row_height+scrollbar)
            else:
                self.assertGreaterEqual(panel.GetSize().height,row_height)
            self.assertIs(self.window.jump_button.GetParent(),panel)

    def test_view_meaning_survives_fbp_option_reordering(self):
        for choices in (('Visual items','Pages','Sources'),('Sources','Visual items','Pages')):
            self.window.view_choice.Set(list(choices))
            for caption,semantic in (('Sources',0),('Pages',1),('Visual items',2)):
                self.window.view_choice.SetStringSelection(caption)
                self.window.change_view(None)
                self.assertEqual(self.window.view,semantic)
                self.assertEqual(self.window.index_table.GetItemCount(),self.catalog.rows(semantic))
            self.window._choose_view(2)
            self.assertEqual(self.window.view_choice.GetStringSelection(),'Visual items')

    def test_fbp_sections_do_not_overlap_or_clip_toolbar_vertically(self):
        panel=self.window.m_search_txt.GetParent()
        controls=[self.window.view_choice,self.window.m_search_txt,self.window.b_last_txt,
                  self.window.b_next_txt,self.window.refresh_button,self.window.export_button,
                  self.window.locate_main_button,self.window.jump_button]
        self.assertIsInstance(self.window.index_details_splitter.GetContainingSizer(),self.wx.FlexGridSizer)
        for width,height in ((750,440),(900,520),(1400,900)):
            self.window.SetSize((width,height));self.window.Layout()
            self.window.resize_controls_row(None);self.window.Layout();self.app.Yield(True)
            sections=[self.window.summary,panel,self.window.match_label,
                      self.window.index_table,self.window.path_details]
            def rect(control):return self.wx.Rect(control.ClientToScreen((0,0)),control.GetSize())
            for upper,lower in zip(sections,sections[1:]):
                self.assertLess(rect(upper).GetBottom(),rect(lower).GetTop())
            self.assertLess(rect(self.window.path_details).GetBottom(),rect(self.window.copy_source_button).GetTop())
            self.assertLess(rect(self.window.copy_source_button).GetBottom(),
                            self.window.ClientToScreen((0,self.window.GetClientSize().height)).y)
            for control in controls:
                self.assertGreaterEqual(control.GetPosition().y,0)
                self.assertLess(control.GetRect().GetBottom(),panel.GetClientSize().height)

    def test_flex_grid_grows_splitter_and_keeps_detail_height_on_window_resize(self):
        root=self.window.index_details_splitter.GetContainingSizer()
        self.assertIsInstance(root,self.wx.FlexGridSizer)
        self.assertTrue(root.IsRowGrowable(3))
        for row in (0,1,2,4):self.assertFalse(root.IsRowGrowable(row))
        self.window.SetSize((1100,520));self.window.Layout();self.app.Yield(True)
        panel=self.window.m_search_txt.GetParent()
        toolbar=panel.GetSize().height
        table=self.window.index_table.GetSize().height
        self.window.SetSize((1100,720));self.window.Layout();self.app.Yield(True)
        self.assertEqual(panel.GetSize().height,toolbar)
        self.assertEqual(self.window.index_table.GetSize().height-table,200)

    def test_splitter_adjusts_both_heights_without_losing_path_selection(self):
        self.window.SetSize((1100,720));self.window.Layout();self.app.Yield(True)
        splitter=self.window.index_details_splitter
        self.assertIsInstance(splitter,self.wx.SplitterWindow)
        self.assertTrue(splitter.IsSplit())
        self.assertEqual(splitter.GetSplitMode(),self.wx.SPLIT_HORIZONTAL)
        self.assertTrue(splitter.HasFlag(self.wx.SP_LIVE_UPDATE))
        self.window._select_index(0)
        text=self.window.path_details.GetValue()
        initial=splitter.GetSashPosition()
        table=self.window.index_table.GetSize().height
        details=self.window.path_details.GetSize().height
        splitter.SetSashPosition(initial-60);self.app.Yield(True)
        self.assertEqual(self.window.path_details.GetSize().height,details+60)
        self.assertEqual(self.window.index_table.GetSize().height,table-60)
        splitter.SetSashPosition(initial+20);self.app.Yield(True)
        self.assertEqual(self.window.path_details.GetSize().height,details-20)
        self.assertEqual(self.window.index_table.GetSize().height,table+20)
        self.assertEqual(self.window.path_details.GetValue(),text)
        self.assertGreaterEqual(splitter.GetMinimumPaneSize(),80)

    def test_export_streams_rows_to_excel(self):
        import zipfile
        target=Path(self.temp.name)/'video_index_sources.xlsx'
        self.window._export(target)
        self.pump(lambda:target.exists() and self.window.export_button.IsEnabled())
        with zipfile.ZipFile(target) as archive:
            text=archive.read('xl/worksheets/sheet2.xml').decode('utf-8')
        self.assertIn('two.mp4',text)
        self.assertIn('7-13',text)
        self.assertFalse(list(target.parent.glob('.index_excel_*')))

    def test_views_only_show_relevant_columns(self):
        expected={0:['Video #','Pages','Frames','Video path','Last frame time (s)','Sample step'],
                  1:['Page','Videos','Frame ranges','Time ranges (s)','Video paths'],
                  2:['Visual ID','Page','Video','Frame / time','Original video','Position','Frame path','Algorithm','Algorithm path','Cache state']}
        for view,headers in expected.items():
            self.window._choose_view(view);self.window.change_view(None)
            control=self.window.index_table
            self.assertEqual(control.GetColumnCount(),len(headers))
            self.assertEqual([control.GetColumn(i).GetText() for i in range(control.GetColumnCount())],headers)
            self.assertTrue(control.GetItemText(0,control.GetColumnCount()-1))

    def test_summary_reports_loaded_sequential_images_not_parallel(self):
        self.window.catalog=TimelineTests().model(video=False,serial=False,kind=2,sequential=True)
        self.window.change_view(None)
        self.assertIn('Image | Sequential | 1 pages |',self.window.summary.GetLabel())

    def test_summary_keeps_video_file_list_input_separate_from_order(self):
        self.window.catalog.input_mode='Image File List'
        self.window.change_view(None)
        self.assertIn('Video | Image File List | 13 pages |',self.window.summary.GetLabel())



if __name__=='__main__':unittest.main()
