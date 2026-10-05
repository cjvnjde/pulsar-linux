import json
from copy import deepcopy
from pathlib import Path
import unittest
from pulsar3.editor_model import ProfileDocument, append_tap, macro_bytes, move_dpi_stage, new_macro, remove_macro
from pulsar3.protocol import encode_macro, plan
from pulsar3.recorder import Recording

ROOT=Path(__file__).resolve().parents[1]

class EditorModelTests(unittest.TestCase):
    def setUp(self):self.config=json.loads((ROOT/'pulsar3/data/default.json').read_text())

    def test_saved_and_applied_are_independent_snapshots(self):
        doc=ProfileDocument(self.config)
        self.assertFalse(doc.dirty);self.assertTrue(doc.pending)
        doc.config['dpi'][0]=900;snapshot=doc.validated()
        doc.mark_saved(snapshot)
        self.assertFalse(doc.dirty);self.assertTrue(doc.pending)
        doc.mark_applied(snapshot);doc.config['dpi'][0]=1000
        self.assertTrue(doc.dirty);self.assertTrue(doc.pending)
        self.assertEqual(snapshot['dpi'][0],900)
        self.assertEqual(doc.applied['dpi'][0],900)

    def test_invalid_load_preserves_editor(self):
        doc=ProfileDocument(self.config);bad=deepcopy(self.config);bad['buttons']['left']='disabled'
        with self.assertRaises(ValueError):doc.load(bad)
        self.assertEqual(doc.config,self.config)

    def test_reorder_dpi_and_custom_color_preserves_applied_snapshot(self):
        self.config['dpi']=[1200,3200,600]
        self.config['dpi_lighting']={'enabled':True,'colors':['#00ff00','#ff0000','#ff00ff']}
        doc=ProfileDocument(self.config);doc.mark_applied(self.config)
        move_dpi_stage(doc.config,2,0)
        self.assertEqual(doc.config['dpi'],[600,1200,3200])
        self.assertEqual(doc.config['dpi_lighting']['colors'],['#ff00ff','#00ff00','#ff0000'])
        packet=plan(doc.validated(),['dpi'])[0]
        self.assertEqual(packet.payload[4],3)
        self.assertEqual(packet.payload[9:15],bytes.fromhex('58 02 b0 04 80 0c'))
        self.assertEqual(doc.applied,self.config)
        self.assertTrue(doc.pending)
        move_dpi_stage(doc.config,0,2)
        self.assertEqual(doc.config,self.config)
        with self.assertRaises(ValueError):move_dpi_stage(doc.config,0,3)
        del doc.config['dpi_lighting']
        move_dpi_stage(doc.config,0,2)
        self.assertEqual(doc.config['dpi'],[3200,600,1200])

    def test_shortcut_tap_is_balanced_and_uploads_before_binding(self):
        macro={'slot':4,'repeat':2,'events':[]};append_tap(macro,6,2000,3)
        self.assertEqual([(e['key'],e['action']) for e in macro['events']],[(224,'down'),(225,'down'),(6,'down'),(6,'up'),(225,'up'),(224,'up')])
        self.assertEqual(macro_bytes(macro),20)
        self.assertEqual(len(encode_macro(macro)),128)
        self.config['macros']=[macro];self.config['buttons']['back']={'macro':4,'mode':'hold'}
        packets=plan(self.config)
        self.assertEqual(packets[0].name,'macro slot 4')

    def test_deleting_macro_restores_all_references(self):
        self.config['macros']=[new_macro(2),new_macro(5)]
        self.config['buttons']['back']={'macro':2,'mode':'once'}
        self.config['buttons']['dpi']={'ui_key':[4,0,2,0]}
        restored=remove_macro(self.config,2)
        self.assertEqual(set(restored),{'back','dpi'})
        self.assertEqual(self.config['buttons']['dpi'],'dpi-cycle')
        self.assertEqual([m['slot'] for m in self.config['macros']],[5]);plan(self.config)

    def test_recorder_ignores_repeat_preserves_physical_release(self):
        r=Recording();r.press(38,4,10);r.press(38,4,10.05);r.release(38,10.10)
        self.assertEqual(r.stop(11),[{'key':4,'action':'down','delay_ms':100},{'key':4,'action':'up','delay_ms':10}])
        encode_macro({'slot':0,'events':r.events})

    def test_focus_loss_releases_all_held_keys_and_quantizes(self):
        r=Recording();r.press(37,224,1);r.press(38,4,1.021);r.stop(3.016)
        self.assertEqual([e['action'] for e in r.events],['down','down','up','up'])
        self.assertEqual(r.events[1]['delay_ms'],2000)
        self.assertEqual(r.events[-1]['delay_ms'],10)
        encode_macro({'slot':0,'events':r.events})

if __name__=='__main__':unittest.main()
