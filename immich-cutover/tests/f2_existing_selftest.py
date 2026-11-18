"""Offline fault injection of each mandatory F2 assertion and Bash conditional context.
Uses synthetic results only. The real SQL/Docker path is covered by f2_existing_rehearsal.py.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import prepare_existing_target as f2
import cutstate
CV=Path(__file__).resolve().parents[1]
results=[]
def test(name,ok):
    results.append(dict(name=name,ok=bool(ok)))
    print(('PASS ' if ok else 'FAIL ')+name,flush=True)

def fails(fn):
    try: fn()
    except Exception: return True
    return False

empty=dict(relations=0,functions=0,schemas=['public'],extensions={'plpgsql':'1.0'},extra_objects=0)
role=dict(oid=7,login=True,inherit=True,super=False,createdb=False,createrole=False,repl=False,bypass=False,memberships=0,scram=True)
rights=dict(connect=True,create=True,temp=True,usage=True,schema_create=True,schema_owner='pg_database_owner')
platform=dict(version='160016',postgis=0,encryption='scram-sha-256',preload='vchord',available=f2.cl.EXPECTED_EXT,hba=[dict(type='host',address='all',auth_method='scram-sha-256',error=None)])
for name,value,checker in [('empty',empty,f2.check_empty),('role',role,lambda x:f2.check_role(x,role)),('rights',rights,f2.check_rights),('platform',platform,f2.check_platform)]:
    test(name+' positive',not fails(lambda:checker(value)))
    for key in value:
        x=copy.deepcopy(value);x[key]=None
        test(name+' corrupt '+key,fails(lambda:checker(x)))
    for x in ('',None,{},[],True,False,'t','f'):
        test(name+' rejects incomplete '+repr(x),fails(lambda:checker(x)))
for v in (False,'t','f',1,0,None):
    x=dict(rights,connect=v);test('strict CONNECT JSON bool '+repr(v),fails(lambda:f2.check_rights(x)))
# Python bool==1 is normally true: the validator must reject integer pseudo-booleans.
test('mount order ignored',f2.canonical_mounts([dict(a=1),dict(a=2)])==f2.canonical_mounts([dict(a=2),dict(a=1)]))
test('mount content retained',f2.canonical_mounts([dict(a=1)])!=f2.canonical_mounts([dict(a=2)]))
test('mount duplicates retained',f2.canonical_mounts([dict(a=1)])!=f2.canonical_mounts([dict(a=1),dict(a=1)]))
good=subprocess.CompletedProcess([],0,'immich\n','');bad=subprocess.CompletedProcess([],2,'','password authentication failed')
test('SCRAM positive+negative',not fails(lambda:f2.check_login(good,bad)))
for p in [subprocess.CompletedProcess([],0,'',''),subprocess.CompletedProcess([],1,'','network error'),subprocess.CompletedProcess([],2,'','connection refused')]:
    test('SCRAM rejects negative rc'+str(p.returncode),fails(lambda:f2.check_login(good,p)))
for p in [subprocess.CompletedProcess([],1,'immich',''),subprocess.CompletedProcess([],0,'',''),subprocess.CompletedProcess([],0,'postgres','')]:
    test('SCRAM rejects invalid positive',fails(lambda:f2.check_login(p,bad)))
# Every mandatory require in validate is failed in turn. All external inputs have
# otherwise-valid synthetic structures. Failure must throw before journal append.
with tempfile.TemporaryDirectory(prefix='immich-apptest-f2-unit-') as td:
    root=Path(td);ev=root/'ev';ev.mkdir();old=root/'old';old.mkdir()
    containers={'db':dict(State=dict(Running=True,Health=dict(Status='healthy')),Config=dict(Env=[]),HostConfig=dict(PortBindings={}),NetworkSettings=dict(Ports={},Networks={'net':dict(IPAddress='10.0.0.2')})),
                'srv':dict(State=dict(Running=True,Health=dict(Status='healthy')),Config=dict(Env=['DB_HOSTNAME=src','DB_DATABASE_NAME=immich','DB_USERNAME=immich']))}
    identity=dict(oid=9,owner='immich',acl=None,encoding='UTF8',collate='en_US.utf8',ctype='en_US.utf8')
    p=dict(id='testf2unit',ev=str(ev),prev_ev=str(old),prev_tip='tip',prev_entries=1,home=td,target='db',server='srv',source='src',network='net',role=role,new_identity=identity,archive_identity=dict(identity,oid=8),archive='archive',archive_snapshot=td,archive_probe=td,containers={'db':1,'srv':1},protected={str(root/'config'):'sha'})
    def sql(c,q,**kw):
        if 'server_version_num' in q:return platform
        if 'pg_authid' in q:return role
        if 'SET LOCAL ROLE' in q:return rights
        return 0
    def setup_mocks():
        from contextlib import ExitStack
        st=ExitStack()
        mocks=[patch.object(f2,'authorize'),patch.object(f2,'real_path',side_effect=Path),patch.object(f2,'digest',return_value='sha'),
               patch.object(f2,'backup_verify'),patch.object(f2,'inspect',side_effect=lambda n:containers[n]),patch.object(f2,'signature',return_value=1),
               patch.object(f2,'db_identity',side_effect=lambda c,n:identity if n=='immich' else p['archive_identity']),
               patch.object(f2,'empty_database',return_value=empty),patch.object(f2,'read_json',return_value={}),
               patch.object(f2.cl,'TARGET','db'),patch.object(f2.cl,'SERVER','srv'),patch.object(f2.cl,'SOURCE','src'),patch.object(f2.cl,'pj',side_effect=sql),
               patch.object(f2.cl,'container_env',return_value='synthetic'),patch.object(f2.cl,'run',side_effect=[good,bad]),
               patch.object(f2.db_snapshot,'snapshot'),patch.object(f2.write_probe,'capture'),patch.object(f2.write_probe,'check',return_value={'status':'PASS'}),
               patch.object(f2.cutstate,'load',side_effect=lambda path:('ROLLED_BACK','tip',[1]) if str(path)==str(old) else ('NONE','',[])),
               patch.dict(os.environ,CUTOVER_ID=p['id'],EV=p['ev'])]
        for m in mocks:st.enter_context(m)
        return st
    calls=[];original=f2.require
    with setup_mocks(),patch.object(f2,'require',side_effect=lambda ok,n:(calls.append(n),original(ok,n))[1]):
        f2.validate(p,root,emit=lambda _:None)
    test('full validator synthetic positive',bool(calls))
    for index,name in enumerate(calls):
        counter=[-1];commits=[]
        def injected(ok,n):
            counter[0]+=1
            original(False if counter[0]==index else ok,n)
        with setup_mocks(),patch.object(f2,'require',side_effect=injected):
            failed=fails(lambda:f2.execute(p,root,True,journal=lambda *a:commits.append(a)))
        test('HALT no PREPARED assertion '+str(index)+' '+name,failed and not commits and not (ev/'state').exists())
    # Simulate mandatory external failures, malformed JSON, missing evidence and SQL errors.
    for object_,method in [(f2,'backup_verify'),(f2,'inspect'),(f2,'db_identity'),(f2,'read_json'),(f2.cl,'pj'),(f2.cl,'container_env'),(f2.cl,'run'),(f2.db_snapshot,'snapshot'),(f2.write_probe,'capture'),(f2.write_probe,'check')]:
        commits=[]
        with setup_mocks(),patch.object(object_,method,side_effect=RuntimeError('injected')):
            failed=fails(lambda:f2.execute(p,root,True,journal=lambda *a:commits.append(a)))
        test('external failure '+method+' HALT without PREPARED',failed and not commits)
# Receipt storage errors must also precede the journal append.
with tempfile.TemporaryDirectory(prefix='immich-apptest-f2-receipt-') as td:
    commits=[]
    with patch.object(f2,'authorize'),patch.object(f2.os,'fsync',side_effect=OSError('disk error')):
        failed=fails(lambda:f2.execute({'id':'synthetic'},Path(td),True,validator=lambda *a:None,journal=lambda *a:commits.append(a)))
    test('receipt fsync failure HALT without PREPARED',failed and not commits)
with patch.object(f2.cl,'REHEARSAL',False),patch.dict(os.environ,{'CUTOVER_APPROVED':''}):
    test('missing production approval rejected',fails(lambda:f2.authorize({'id':'synthetic'},True)))
with patch.object(f2.cl,'REHEARSAL',False),patch.dict(os.environ,{'CUTOVER_APPROVED':'another-id'}):
    test('wrong production approval rejected',fails(lambda:f2.authorize({'id':'synthetic'},True)))
for pseudo in (False,True,'0','',None):
    x=dict(empty,relations=pseudo);test('empty count type '+repr(pseudo),fails(lambda:f2.check_empty(x)))

# Real Bash function + actual journal, Python validator failures, if/&&/||/! contexts.
for context in ('direct','if','and','or','not'):
    for fault in ('validator','journal','success'):
        with tempfile.TemporaryDirectory(prefix='immich-apptest-f2-bash-') as td:
            env=dict(os.environ,CV=str(CV),EV=td,FAULT=fault)
            call={'direct':'s_prepare_existing_target; rc=$?', 'if':'if s_prepare_existing_target; then rc=0; else rc=$?; fi',
                  'and':'s_prepare_existing_target && true; rc=$?', 'or':'s_prepare_existing_target || rc=$?; rc=${rc:-0}',
                  'not':'if ! s_prepare_existing_target; then rc=1; else rc=0; fi'}[context]
            script=r'''
unset CUTOVER_APPROVED
export CUTOVER_REHEARSAL=1 CUTOVER_ID=unitf2 PG_SRC=immich-apptest-src PG_NEW=immich-apptest-db SRV=immich-apptest-server MOPS= BRG= F2_EXISTING_POLICY=/tmp/immich-apptest-policy
source "$CV/steps.sh" || exit 90
python3() {
 case " $* " in
 *prepare_existing_target.py*)
   [ "$FAULT" != validator ] || return 73
   [ "$FAULT" != journal ] || return 74
   command python3 -I "$CV/cutstate.py" set "$EV" --from NONE --to PREPARED; return $?;;
 *) command python3 "$@"; return $?;;
 esac
}
'''+call+'\nprintf "CALL_RC=%s\\n" "$rc"\n'
            proc=subprocess.run(['/bin/bash','--noprofile','--norc','-c',script],env=env,capture_output=True,text=True)
            test('Bash '+context+' '+fault,('CALL_RC=0' in proc.stdout and cutstate.load(td)[0]=='PREPARED') if fault=='success' else ('CALL_RC=0' not in proc.stdout and cutstate.load(td)[0]=='NONE'))
print('RESULT',sum(x['ok'] for x in results),'/',len(results))
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(results,indent=1))
sys.exit(0 if all(x['ok'] for x in results) else 1)
