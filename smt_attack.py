#!/usr/bin/env python3
"""Exact QF_BV encoding of CPWI, using the public Z3 C API via ctypes.

Requires a Z3 shared library (system libz3 or the z3-solver Python package).
The attacker receives only the public instance and endpoint. No witness hint.
All recovered bit strings must be checked by an independent forward evaluator.
"""
from __future__ import annotations
import ctypes as C
import ctypes.util
import importlib.util
import os
from pathlib import Path
import time

class Z3Library:
    def __init__(self):
        candidates=[]
        if os.getenv('CPWI_Z3_LIBRARY'): candidates.append(os.environ['CPWI_Z3_LIBRARY'])
        spec=importlib.util.find_spec('z3')
        if spec and spec.origin:
            libdir=Path(spec.origin).parent/'lib'
            candidates.extend(str(p) for pattern in ('libz3.so*','libz3.dylib','libz3.dll') for p in libdir.glob(pattern))
        system=C.util.find_library('z3')
        if system: candidates.append(system)
        for candidate in candidates:
            try:
                self.lib=C.CDLL(candidate); self.path=candidate; break
            except OSError: pass
        else:
            raise RuntimeError('Z3 library not found. Install z3-solver or set CPWI_Z3_LIBRARY to libz3.')
        self.functions={}
        P=C.c_void_p; S=C.c_char_p; U=C.c_uint; I=C.c_int; B=C.c_bool
        signatures={
          'mk_config':(P,[]),'del_config':(None,[P]),'mk_context':(P,[P]),'del_context':(None,[P]),
          'mk_string_symbol':(P,[P,S]),'mk_solver':(P,[P]),'solver_inc_ref':(None,[P,P]),'solver_dec_ref':(None,[P,P]),
          'solver_from_string':(None,[P,P,S]),'solver_check':(I,[P,P]),'solver_get_reason_unknown':(S,[P,P]),
          'solver_get_model':(P,[P,P]),'model_inc_ref':(None,[P,P]),'model_dec_ref':(None,[P,P]),
          'model_eval':(B,[P,P,P,B,C.POINTER(P)]),'get_bool_value':(I,[P,P]),'mk_bool_sort':(P,[P]),'mk_const':(P,[P,P,P]),
          'mk_params':(P,[P]),'params_inc_ref':(None,[P,P]),'params_dec_ref':(None,[P,P]),
          'params_set_uint':(None,[P,P,P,U]),'solver_set_params':(None,[P,P,P]),
          'solver_get_statistics':(P,[P,P]),'stats_inc_ref':(None,[P,P]),'stats_dec_ref':(None,[P,P]),'stats_to_string':(S,[P,P]),
          'get_version':(None,[C.POINTER(U)]*4),
        }
        for name,(restype,args) in signatures.items():
            f=getattr(self.lib,'Z3_'+name); f.restype=restype; f.argtypes=args; setattr(self,name,f)
        ver=[U() for _ in range(4)]; self.get_version(*(C.byref(x) for x in ver))
        self.version='.'.join(str(x.value) for x in ver)

    def solve(self, text:str, n:int, *, rlimit:int=2000000, timeout_ms:int=20000, seed:int=17)->dict:
        cfg=self.mk_config(); ctx=self.mk_context(cfg); self.del_config(cfg)
        sol=self.mk_solver(ctx); self.solver_inc_ref(ctx,sol)
        result={}
        try:
            params=self.mk_params(ctx); self.params_inc_ref(ctx,params)
            for key,val in (('rlimit',rlimit),('timeout',timeout_ms),('random_seed',seed)):
                sym=self.mk_string_symbol(ctx,key.encode()); self.params_set_uint(ctx,params,sym,val)
            self.solver_set_params(ctx,sol,params); self.params_dec_ref(ctx,params)
            t=time.perf_counter(); self.solver_from_string(ctx,sol,text.encode()); parse=time.perf_counter()-t
            t=time.perf_counter(); status=self.solver_check(ctx,sol); elapsed=time.perf_counter()-t
            result.update(status={1:'SAT',-1:'UNSAT',0:'UNKNOWN'}[status],parse_seconds=parse,solve_seconds=elapsed,version=self.version)
            result['reason_unknown']=self.solver_get_reason_unknown(ctx,sol).decode() if status==0 else ''
            stat=self.solver_get_statistics(ctx,sol); self.stats_inc_ref(ctx,stat)
            result['statistics_raw']=self.stats_to_string(ctx,stat).decode(); self.stats_dec_ref(ctx,stat)
            if status==1:
                model=self.solver_get_model(ctx,sol); self.model_inc_ref(ctx,model)
                bits=[]
                for i in range(n):
                    symbol=self.mk_string_symbol(ctx,f'b_{i}'.encode())
                    term=self.mk_const(ctx,symbol,self.mk_bool_sort(ctx)); out=C.c_void_p()
                    if not self.model_eval(ctx,model,term,True,C.byref(out)): raise RuntimeError('Model evaluation failed')
                    val=self.get_bool_value(ctx,out)
                    if val not in (-1,1): raise RuntimeError('Non-Boolean witness')
                    bits.append(int(val==1))
                result['witness']=bits; self.model_dec_ref(ctx,model)
        finally:
            self.solver_dec_ref(ctx,sol); self.del_context(ctx)
        return result

def encode(instance, target, *, all_different=True, fixed_bits=None):
    u0,v0,AA,BB=instance; n=len(AA); m=len(u0); k=(m-1).bit_length()
    if n<1 or m<2: raise ValueError('Invalid dimensions')
    if len(target)!=2 or any(len(p)!=m or sorted(p)!=list(range(m)) for p in target): raise ValueError('Target must be a permutation pair')
    lines=['(set-logic QF_BV)']; decl=0; asserts=0
    def bv(v): return f'(_ bv{v} {k})'
    def var(name):
        nonlocal decl
        lines.append(f'(declare-fun {name} () (_ BitVec {k}))'); decl+=1
        if m != 1<<k: ass(f'(bvult {name} {bv(m)})')
        return name
    def ass(expr):
        nonlocal asserts
        lines.append(f'(assert {expr})'); asserts+=1
    def lookup(array,index):
        expr=array[-1]
        for j in range(m-2,-1,-1): expr=f'(ite (= {index} {bv(j)}) {array[j]} {expr})'
        return expr
    for i in range(n): lines.append(f'(declare-fun b_{i} () Bool)')
    U=[[var(f'u_{i}_{j}') for j in range(m)] for i in range(n+1)]
    V=[[var(f'v_{i}_{j}') for j in range(m)] for i in range(n+1)]
    for initial,values in ((U[0],u0),(V[0],v0)):
        for name,value in zip(initial,values): ass(f'(= {name} {bv(value)})')
    for i in range(n):
        for label,old,other,new,constants in (('u',U[i],V[i],U[i+1],AA[i]),('v',V[i],U[i],V[i+1],BB[i])):
            for j in range(m):
                q=var(f'q{label}_{i}_{j}'); r=var(f'r{label}_{i}_{j}')
                ass(f'(= {q} {lookup(other,old[j])})')
                a0=lookup([bv(a) for a in constants[0]],q); a1=lookup([bv(a) for a in constants[1]],q)
                ass(f'(= {r} (ite b_{i} {a1} {a0}))')
                ass(f'(= {new[j]} {lookup(old,r)})')
    if all_different:
        for layer in U+V: ass('(distinct '+' '.join(layer)+')')
    for terminal,values in ((U[n],target[0]),(V[n],target[1])):
        for name,value in zip(terminal,values): ass(f'(= {name} {bv(value)})')
    if fixed_bits is not None:
        if len(fixed_bits)!=n: raise ValueError('Fixed bits have wrong length')
        for i,b in enumerate(fixed_bits): ass(f'(= b_{i} '+('true' if b else 'false')+')')
    text='\n'.join(lines)+'\n'
    return text,{'n':n,'m':m,'bit_width':k,'bool_variables':n,'bv_variables':decl,'assertions':asserts,'smtlib_bytes':len(text.encode())}

if __name__=='__main__':
    from reproduce import generate_cpwi_instance,cpwi_forward,bits_from_int
    z=Z3Library(); print('Z3',z.version,z.path,flush=True)
    for n,m in ((4,5),(8,5),(8,8),(12,6),(16,8)):
        instance=generate_cpwi_instance(n,m,901); x=bits_from_int((1<<n)//3,n); y=cpwi_forward(x,instance)
        text,meta=encode(instance,y); ans=z.solve(text,n,rlimit=1000000,timeout_ms=5000)
        if ans['status']=='SAT': assert cpwi_forward(ans['witness'],instance)==y
        print(n,m,ans,flush=True)
