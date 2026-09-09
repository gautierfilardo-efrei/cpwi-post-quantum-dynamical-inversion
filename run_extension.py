#!/usr/bin/env python3
"""Reproduce the new SMT attack without altering the original CPWI data.
Defaults: 54 planted targets, 20 million Z3 resource units per target.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,platform,random,re,subprocess,sys,time
from pathlib import Path
from reproduce import generate_cpwi_instance,cpwi_forward,bits_from_int
from smt_attack import Z3Library,encode
GRID=tuple((n,m,s) for n in (4,6,8,10,12,16) for m in (5,6,8) for s in (901,902,903))

def target_for(n,m,s):
 h=hashlib.sha256(f'CPWI-SMT-v1|{n}|{m}|{s}'.encode()).digest()
 v=random.Random(int.from_bytes(h,'big')).randrange(1<<n)
 return v,bits_from_int(v,n)

def direct(bits,inst):
 u,v,A,B=inst
 for i,b in enumerate(bits):
  u,v=tuple(u[A[i][b][v[u[j]]]] for j in range(len(u))),tuple(v[B[i][b][u[v[j]]]] for j in range(len(v)))
 return u,v

def dfs_invert(inst,y):
 u0,v0,A,B=inst;n=len(A);m=len(u0);calls=leaves=0
 def rec(i,u,v,path):
  nonlocal calls,leaves
  if i==n:
   leaves+=1;return path if (u,v)==y else None
  for b in (0,1):
   nu=tuple(u[A[i][b][v[u[j]]]] for j in range(m));nv=tuple(v[B[i][b][u[v[j]]]] for j in range(m));calls+=1
   ans=rec(i+1,nu,nv,path+(b,))
   if ans is not None:return ans
  return None
 t=time.perf_counter();ans=rec(0,u0,v0,());dt=time.perf_counter()-t
 if ans is None:raise AssertionError('Planted target not found')
 assert cpwi_forward(ans,inst)==y
 return dict(dfs_round_transitions=calls,dfs_terminal_tests=leaves,dfs_seconds=dt,dfs_witness=list(ans))

def worker(p):
 n,m,s=p['n'],p['m'],p['seed'];z=Z3Library();inst=generate_cpwi_instance(n,m,s);secret,x=target_for(n,m,s);y=cpwi_forward(x,inst)
 assert direct(x,inst)==y
 text,meta=encode(inst,y,all_different=p.get('all_different',True))
 ans=z.solve(text,n,rlimit=p['rlimit'],timeout_ms=p['timeout_ms'],seed=17)
 valid=ans['status']=='SAT' and cpwi_forward(ans['witness'],inst)==y and direct(ans['witness'],inst)==y
 if ans['status']=='SAT' and not valid:raise AssertionError('Invalid model')
 if ans['status']=='UNSAT':raise AssertionError('Unsound encoding')
 r={**meta,'seed':s,'secret_lsb_integer':secret,'target':[list(q) for q in y],'all_different':p.get('all_different',True),'rlimit':p['rlimit'],'timeout_ms':p['timeout_ms'],'solver_seed':17,**ans,'verified_preimage':valid}
 r.update(dfs_invert(inst,y));return r

def run_process(p):
 r=subprocess.run([sys.executable,__file__,'--worker',json.dumps(p)],capture_output=True,text=True,timeout=90)
 if r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return json.loads(r.stdout)

def csvwrite(path,rows):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def unit_tests(out):
 z=Z3Library();records=[]
 for m in (5,6,8):
  n=3;inst=generate_cpwi_instance(n,m,990+m)
  for v in range(8):
   y=cpwi_forward(bits_from_int(v,n),inst)
   for w in range(8):
    b=bits_from_int(w,n);expected=cpwi_forward(b,inst)==y;text,_=encode(inst,y,fixed_bits=b)
    r=z.solve(text,n,rlimit=2000000,timeout_ms=10000)
    if r['status']!=('SAT' if expected else 'UNSAT'):raise AssertionError((m,v,w,r))
    records.append(dict(m=m,n=n,target_input=v,fixed_input=w,expected_sat=expected,status=r['status']))
  reachable={cpwi_forward(bits_from_int(v,n),inst) for v in range(8)}
  for k in range(1,100):
   y=(tuple(range(m)),tuple(range(m))) if k==1 else generate_cpwi_instance(1,m,40000+k)[:2]
   if y not in reachable:break
  text,_=encode(inst,y);r=z.solve(text,n,rlimit=2000000,timeout_ms=10000)
  if r['status']!='UNSAT':raise AssertionError('Unreachable target not certified')
  records.append(dict(m=m,n=n,target_input='unreachable',fixed_input='free',expected_sat=False,status=r['status']))
 csvwrite(out/'encoding_tests.csv',records);return len(records)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker');p.add_argument('--out',type=Path,default=Path(__file__).parent/'extension_results');p.add_argument('--smoke',action='store_true');p.add_argument('--rlimit',type=int,default=20000000);p.add_argument('--timeout-ms',type=int,default=20000);a=p.parse_args()
 if a.worker:print(json.dumps(worker(json.loads(a.worker))));return
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 for d in ('smt2','records'):(out/d).mkdir(exist_ok=True)
 z=Z3Library();print('Z3',z.version,'out',out,flush=True);tests=unit_tests(out);rows=[]
 for n,m,s in (GRID[:3] if a.smoke else GRID):
  r=run_process(dict(n=n,m=m,seed=s,rlimit=a.rlimit,timeout_ms=a.timeout_ms));stem=f'n{n}_m{m}_seed{s}'
  inst=generate_cpwi_instance(n,m,s);text,_=encode(inst,tuple(tuple(q) for q in r['target']))
  export = (f'(set-option :rlimit {a.rlimit})\n(set-option :timeout {a.timeout_ms})\n(set-option :random-seed 17)\n' + text + '(check-sat)\n')
  (out/'smt2'/f'{stem}.smt2').write_text(export);(out/'records'/f'{stem}.json').write_text(json.dumps(r,indent=2)+'\n')
  st=dict(re.findall(r':([^\s()]+)\s+([^\s()]+)',r['statistics_raw']));scalar={k:v for k,v in r.items() if not isinstance(v,(list,dict)) and k!='statistics_raw'}
  scalar['resource_count']=st.get('rlimit-count','');scalar['conflicts']=st.get('sat-conflicts',st.get('conflicts',''));scalar['decisions']=st.get('sat-decisions',st.get('decisions',''));scalar['smt2_sha256']=hashlib.sha256(export.encode()).hexdigest()
  rows.append(scalar);csvwrite(out/'smt_results.csv',rows);print(n,m,s,r['status'],round(r['solve_seconds'],3),'DFS',r['dfs_round_transitions'],flush=True)
 env=dict(python=sys.version,platform=platform.platform(),processor=platform.processor(),z3_version=z.version,z3_library=z.path,encoding_test_cases=tests,cases=len(rows),resource_budget=a.rlimit,timeout_ms=a.timeout_ms,note='Fresh subprocess per target; default single solver; no solution hints; all cases retained.')
 for name in ('run_extension.py','smt_attack.py','reproduce.py'):
  path=Path(__file__).with_name(name);env.setdefault('source_sha256',{})[name]=hashlib.sha256(path.read_bytes()).hexdigest()
 (out/'environment.json').write_text(json.dumps(env,indent=2)+'\n');print('DONE',len(rows),sum(r['status']=='SAT' for r in rows),'SAT',tests,'tests',flush=True)
if __name__=='__main__':main()
