"""Bounded-memory, atomic Excel exports for all index views."""
import os
import tempfile
from concurrent.futures import CancelledError
from datetime import datetime, timezone
from pathlib import Path
from .index_columns import VIEW_NAMES, view_columns, view_row

EXCEL_ROWS = 1048576
MAX_TEXT_UNITS = 32000


def _text_parts(value):
    """Excel counts UTF-16 code units, not Python Unicode code points."""
    encoded = value.encode('utf-16-le')
    start = 0
    while start < len(encoded):
        end = min(len(encoded),start+MAX_TEXT_UNITS*2)
        if end < len(encoded) and 0xD800 <= int.from_bytes(encoded[end-2:end],'little') <= 0xDBFF:
            end -= 2
        yield encoded[start:end].decode('utf-16-le')
        start = end


def write_index_xlsx(path, model, view, cancelled=lambda:False, cache_states=None, sheet_rows=EXCEL_ROWS):
    try:
        from xlsxwriter import Workbook
    except ImportError as error:
        raise RuntimeError('Excel export requires XlsxWriter; install the updated requirements.txt') from error
    if not 2 <= sheet_rows <= EXCEL_ROWS:
        raise ValueError('Invalid Excel worksheet row limit')
    path = Path(path)
    columns = view_columns(view,model.video)
    cache_states = cache_states or {}
    total = model.rows(view)
    with tempfile.TemporaryDirectory(prefix='.index_excel_',dir=path.parent) as work:
        temporary = Path(work)/'index.xlsx'
        with Workbook(str(temporary), {'constant_memory': True, 'strings_to_formulas': False,
                                      'strings_to_urls': False, 'tmpdir': work, 'use_zip64': True}) as workbook:
            title = workbook.add_format({'bold':True,'font_color':'white','bg_color':'#30577E',
                                         'text_wrap':True,'valign':'vcenter'})
            body = workbook.add_format({'text_wrap':True,'valign':'top'})
            info = workbook.add_worksheet('Info')
            info.set_column(0,0,24); info.set_column(1,1,70)
            for row,values in enumerate((('View',VIEW_NAMES[view]),('Media','Video' if model.video else 'Image'),
                                        ('Input mode',getattr(model,'input_mode','Input')),
                                        ('Order',model.order),('Records',total),
                                        ('Created UTC',datetime.now(timezone.utc).isoformat()),
                                        ('Cache state','Snapshot of checked files; Not checked does not mean missing'),
                                        ('Long text','Cells beyond Excel text limits continue in Long text sheets'))):
                info.write_row(row,0,values,body)
            sheet = None; row = 0; number = 0
            long_sheet = None; long_row = 0; long_number = 0
            for index in range(max(1,total)):
                if cancelled():
                    raise CancelledError('Index export canceled')
                if sheet is None or row >= sheet_rows:
                    if sheet is not None:sheet.autofilter(0,0,row-1,len(columns)-1)
                    number += 1
                    sheet = workbook.add_worksheet(f'{VIEW_NAMES[view]} {number}')
                    sheet.freeze_panes(1,1)
                    for col,column in enumerate(columns):sheet.set_column(col,col,max(10,min(75,column.width/7)))
                    sheet.set_row(0,30)
                    sheet.write_row(0,0,[c.label for c in columns],title)
                    row = 1
                if not total:break
                values = list(view_row(model,view,index))
                if view == 2:
                    entry = model.visual_entry(index)
                    frame_path = entry['path']
                    cached = model.video or entry.get('processed',False)
                    state = cache_states.get(frame_path)
                    values[-1] = ('Not checked' if state is None else
                                  ('Cached' if cached else 'Exists') if state else
                                  ('Virtual / not cached' if cached else 'Missing'))
                for col,value in enumerate(values):
                    if not isinstance(value,str) or len(value) < 16000:
                        continue
                    parts = iter(_text_parts(value))
                    first = next(parts,'')
                    rest = next(parts,None)
                    if rest is None:continue
                    values[col] = first+'\n[Full text continues in Long text sheets]'
                    def all_parts():
                        yield first
                        yield rest
                        yield from parts
                    for part,chunk in enumerate(all_parts(),1):
                        if long_sheet is None or long_row >= sheet_rows:
                            long_number += 1
                            long_sheet = workbook.add_worksheet(f'Long text {long_number}')
                            long_sheet.freeze_panes(1,0)
                            long_sheet.set_column(0,0,20);long_sheet.set_column(1,3,12);long_sheet.set_column(4,4,75)
                            long_sheet.write_row(0,0,('Sheet','Excel row','Column','Part','Text'),title)
                            long_row = 1
                        long_sheet.write_row(long_row,0,(sheet.name,row+1,columns[col].label,part,chunk),body)
                        long_row += 1
                sheet.write_row(row,0,values,body)
                row += 1
            if sheet is not None:sheet.autofilter(0,0,max(0,row-1),len(columns)-1)
        if cancelled():
            raise CancelledError('Index export canceled')
        os.replace(temporary,path)
    return total
