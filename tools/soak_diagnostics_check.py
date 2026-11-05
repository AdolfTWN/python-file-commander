"""Negative control: endurance must fail on a real Tcl background error.

Native Windows groups must select interaction_soak_check.py alongside this check
so its fixed companion script is included in the request's staged manifest.
"""
from pathlib import Path
import subprocess
import sys

child=[sys.executable,str(Path(__file__).with_name('interaction_soak_check.py'))]
if 'pfc' in sys.argv:child.append('pfc')
child.extend(['--seconds','5','--inject-tcl-error'])
result=subprocess.run(child,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=35)
assert result.returncode!=0,'Endurance silently passed despite an injected native Tcl error'
assert b'tk.background.failed' in result.stdout,'Child failed without observing the injected diagnostic'
print('PASS: real Tcl background error is automatically logged and fails the endurance observer')
