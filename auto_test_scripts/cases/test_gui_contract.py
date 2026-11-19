"""FBP names/events and persisted choice indices must match generated GUI code."""
import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

GUI=Path(__file__).resolve().parents[2]/'src/mulimgviewer/gui'
CONTROLS={'wxCollapsiblePane','wxButton','wxTextCtrl','wxChoice','wxSlider','wxCheckBox','wxColourPickerCtrl',
    'wxListCtrl','wxSplitterWindow','wxPanel','wxScrolledWindow','wxStaticText','wxToggleButton',
    'wxSpinCtrl','wxSearchCtrl','wxStatusBar'}


def project(name):
    return GUI/(name+'.fbp')


class GuiContractTests(unittest.TestCase):
    def test_panels_do_not_have_control_only_validator_properties(self):
        for name in ('main_gui','index_table_gui'):
            for panel in ET.parse(project(name)).findall(".//object[@class='wxPanel']"):
                unsupported=[p.get('name') for p in panel.findall('property')
                             if p.get('name','').startswith('validator_')]
                self.assertEqual(unsupported,[],f'{name}: wxPanel has unsupported validators')

    def test_gui_imports_from_source_checkout_and_installed_package(self):
        import subprocess
        import sys
        root=GUI.parents[2]
        for base,package in ((root,'src.mulimgviewer'),(root/'src','mulimgviewer')):
            with self.subTest(package=package):
                code=(f'import sys; sys.path.insert(0,{str(base)!r}); '
                      f'from {package}.gui.main_gui import MulimgViewerGui; '
                      f'from {package}.src.settings_section import SettingsSection')
                result=subprocess.run([sys.executable,'-I','-c',code],cwd=root,
                                      capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)

    def test_fbp_control_names_are_present_in_generated_modules(self):
        for name in ('main_gui','index_table_gui'):
            fbp=ET.parse(project(name))
            tree=ast.parse((GUI/(name+'.py')).read_text(encoding='utf-8-sig'))
            actual={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)
                and isinstance(node.value,ast.Name) and node.value.id=='self' and isinstance(node.ctx,ast.Store)}
            for obj in fbp.findall('.//object'):
                prop=obj.find("property[@name='name']")
                if obj.get('class') in CONTROLS and prop is not None:
                    with self.subTest(gui=name,control=prop.text):self.assertIn(prop.text,actual,'Regenerate GUI from FBP')

    def test_fbp_event_handlers_exist_in_generated_modules(self):
        for name in ('main_gui','index_table_gui'):
            fbp=ET.parse(project(name))
            tree=ast.parse((GUI/(name+'.py')).read_text(encoding='utf-8-sig'))
            methods={node.name for node in ast.walk(tree) if isinstance(node,ast.FunctionDef)}
            for event in fbp.findall('.//event'):
                if event.text and event.text.strip():
                    with self.subTest(gui=name,event=event.get('name'),handler=event.text.strip()):
                        self.assertIn(event.text.strip(),methods,'Regenerate GUI from FBP')

    def test_format_power_and_input_choices_keep_fbp_order_and_defaults(self):
        import re
        expected={}
        for obj in ET.parse(project('main_gui')).findall('.//object'):
            name=obj.find("property[@name='name']")
            if name is not None and name.text in ('save_format','cache_save_format','power_mode','choice_input_mode'):
                expected[name.text]=(re.findall(r'"([^"]*)"',obj.find("property[@name='choices']").text),
                    int(obj.find("property[@name='selection']").text))
        tree=ast.parse((GUI/'main_gui.py').read_text(encoding='utf-8-sig'))
        choices={};selections={}
        constants={target.id:ast.literal_eval(node.value) for node in ast.walk(tree)
            if isinstance(node,ast.Assign) and isinstance(node.value,(ast.List,ast.Tuple))
            for target in node.targets if isinstance(target,ast.Name)}
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call):
                for target in node.targets:
                    if isinstance(target,ast.Attribute) and target.attr in expected:
                        values=next((kw.value for kw in node.value.keywords if kw.arg=='choices'),None)
                        if values is None and len(node.value.args)>4:values=node.value.args[4]
                        if values is not None:choices[target.attr]=constants[values.id] if isinstance(values,ast.Name) else ast.literal_eval(values)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='SetSelection':
                owner=node.func.value
                if isinstance(owner,ast.Attribute) and owner.attr in expected:selections[owner.attr]=ast.literal_eval(node.args[0])
        self.assertEqual({key:(choices[key],selections[key]) for key in expected},expected)
        self.assertEqual(expected['save_format'],(['jpg','png','pdf'],0))
        self.assertEqual(expected['cache_save_format'][0],['jpg','png','auto'])


if __name__=='__main__':unittest.main()
