"""Focused V0.4.2 offline retrieval tests. Never execute target source code."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agents'))
import repository_search as s
import proposal_bridge as bridge
import readonly_investigate as inv

class RetrievalV042(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.hive = Path(t.name) / 'hive'
        self.repo = self.hive / 'work' / 'trivia-lobby'
        self.repo.mkdir(parents=True)
        self.git('init','-q')
        self.git('config','user.name','Fixture')
        self.git('config','user.email','fixture@example.invalid')
        (self.repo/'src').mkdir()
        for i in range(610):
            (self.repo/'src'/f'part{i:03}.ts').write_text(f'export const item{i} = "normal";\n')
        (self.repo/'src'/'part609.ts').write_text('const last = "special_reconnect_value";\n')
        self.git('add','.')
        self.git('-c','core.hooksPath=/dev/null','commit','-qm','fixture')
        self.git('switch','-qc','bee/test')
        for key,val in {'HIVE':self.hive,'WORK':self.repo,'STOP':self.hive/'STOP',
                        'REPORTS':self.hive/'proposals','LOGS':self.hive/'logs'}.items():
            old=getattr(inv,key)
            setattr(inv,key,val)
            self.addCleanup(setattr,inv,key,old)

    def git(self,*args):
        return subprocess.run(['git','-C',str(self.repo),*args],
                              capture_output=True,text=True,check=True).stdout.strip()

    def test_search_beyond_400_files_and_no_writes(self):
        r=s.search(self.repo,'special_reconnect_value',mode='literal')
        self.assertEqual(r['searched_files'],610)
        self.assertFalse(r['partial_scan'])
        self.assertEqual(r['hits'][0]['path'],'src/part609.ts')
        self.assertEqual(r['source_commit'],self.git('rev-parse','HEAD'))
        self.assertEqual(self.git('status','--porcelain'),'')

    def test_batch_reads_once(self):
        old=subprocess.run
        calls=[]
        def inspect(cmd,*a,**kw):
            if 'cat-file' in cmd: calls.append(cmd)
            return old(cmd,*a,**kw)
        with patch.object(s.subprocess,'run',side_effect=inspect):
            s.search(self.repo,'special_reconnect_value')
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][-2:],['cat-file','--batch'])

    def test_budget_disclosed(self):
        with patch.object(s,'MAX_SCAN_BYTES',120):
            r=s.search(self.repo,'special_reconnect_value')
        self.assertTrue(r['partial_scan'])
        self.assertGreater(r['omitted_due_to_budget'],0)
        self.assertLessEqual(r['bytes_scanned'],120)

    def test_corrupted_batch_fails(self):
        oid='a'*40
        with patch.object(s.subprocess,'run',return_value=subprocess.CompletedProcess([],0,b'bad\n',b'')):
            with self.assertRaises(s.RepositorySearchError):
                s._batch_read_blobs(self.repo,[('src/part001.ts',oid,5)])

    def test_uncommitted_never_read(self):
        (self.repo/'src'/'part609.ts').write_text('not_committed_marker\n')
        self.assertEqual(s.search(self.repo,'not_committed_marker',mode='literal')['hits'],[])

    def test_large_file_source_window_and_full_screen(self):
        p=self.repo/'src'/'big.ts'
        lines=[f'// filler {i}: neutral filler text\n' for i in range(500)]
        lines[450]='const special_reconnect_value = room.toUpperCase();\n'
        p.write_text(''.join(lines))
        self.git('add','.')
        self.git('-c','core.hooksPath=/dev/null','commit','-qm','large')
        head=self.git('rev-parse','HEAD')
        evidence=inv.evidence('special_reconnect_value')
        self.assertTrue(any(x['path']=='src/big.ts' and x['line']==451 for x in evidence['evidence']))
        source=bridge._source_file(head,'src/big.ts',[{'path':'src/big.ts','line':451}])
        self.assertIn('COMMITTED SOURCE LINES 439-463',source)
        self.assertNotIn('filler 0:',source)
        self.assertLessEqual(len(source.encode()),bridge.MAX_MODEL_SOURCE_BYTES)
        lines[9]='const api_key = "never expose";\n'
        p.write_text(''.join(lines))
        self.git('add','.')
        self.git('-c','core.hooksPath=/dev/null','commit','-qm','sensitive')
        with self.assertRaises(bridge.ProposalError):
            bridge._source_file(self.git('rev-parse','HEAD'),'src/big.ts',
                                [{'path':'src/big.ts','line':451}])

    def test_refuse_unsubstantiated_window(self):
        p=self.repo/'src'/'big.ts'
        p.write_text('// safe filler\n'*1200)
        self.git('add','.')
        self.git('-c','core.hooksPath=/dev/null','commit','-qm','large')
        with self.assertRaises(bridge.ProposalError):
            bridge._source_file(self.git('rev-parse','HEAD'),'src/big.ts',
                                [{'path':'src/big.ts','line':99999}])

if __name__=='__main__':
    unittest.main()
