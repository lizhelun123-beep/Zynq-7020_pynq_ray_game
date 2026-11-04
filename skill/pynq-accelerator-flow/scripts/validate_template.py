"""Offline source/Notebook/Tcl syntax only;no vendor interpreter or PYNQ import."""
import ast
import json
from pathlib import Path


def validate():
    root = Path(__file__).resolve().parents[1]
    assets = root / 'assets/scalar-demo'
    rtl = root / 'assets/rtl-demo'
    python = sorted(assets.rglob('*.py')) + sorted(rtl.rglob('*.py')) + sorted((root / 'scripts').glob('*.py'))
    for path in python:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        if assets / 'python' in path.parents or rtl / 'python' in path.parents:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=6)
    notebook_path = assets / 'notebooks/scalar_demo.ipynb'
    notebook = json.loads(notebook_path.read_text(encoding='utf-8'))
    if notebook.get('nbformat') != 4:
        raise ValueError('expected Notebook v4')
    cells = 0
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            if cell.get('outputs') or cell.get('execution_count') is not None:
                raise ValueError('template must not ship stale execution outputs')
            compile(''.join(cell['source']), str(notebook_path), 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            cells += 1
    import tkinter
    tcl = tkinter.Tcl()
    scripts = sorted(assets.rglob('*.tcl')) + sorted(rtl.rglob('*.tcl'))
    for path in scripts:
        if not int(tcl.call('info', 'complete', path.read_text(encoding='utf-8'))):
            raise ValueError('incomplete Tcl: ' + str(path))
    return dict(scope='HOST_SOURCE_SYNTAX_ONLY', python_files=len(python), notebook_code_cells=cells,
                tcl_files=len(scripts), tcl_check='info complete only', vendor_tools='NOT_RUN', hardware='NOT_RUN')


if __name__ == '__main__':
    print(json.dumps(validate(), ensure_ascii=False))
