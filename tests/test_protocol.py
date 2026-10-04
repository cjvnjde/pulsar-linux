import copy,json,struct,unittest
from pathlib import Path
from pulsar3.protocol import *
ROOT=Path(__file__).resolve().parents[1]

class ProtocolTests(unittest.TestCase):
    def setUp(self): self.config=json.loads((ROOT/'profiles/default.json').read_text())
    def test_original_machine_code_packets(self):
        fixtures=json.loads((ROOT/'research/reference-packets.json').read_text())
        generated={'sync':sync_packet(),'parameters0_profile0':parameter0(bytes(range(64)),0),
                   'parameters0_profile3':parameter0(bytes(range(64)),3),
                   'parameters1_mask1':parameter1(bytes(range(192)),1),
                   'parameters1_mask7':parameter1(bytes(range(192)),7),
                   'macro_slot0':macro_packet(0,bytes(range(128))),
                   'macro_slot11':macro_packet(11,bytes(range(128))),'dpi_stage2':stage_packet(2)}
        for name,packet in generated.items():
            with self.subTest(name=name):
                self.assertEqual(packet.header.hex(),fixtures[name]['header'])
                self.assertEqual(packet.payload.hex(),fixtures[name]['payload'])
    def test_original_machine_code_button_translation(self):
        for v in json.loads((ROOT/'research/reference-keys.json').read_text()):
            with self.subTest(ui=v['ui']):self.assertEqual(translate_key(v['ui']).hex(),v['wire'])
    def test_original_qml_macro_vectors(self):
        for v in json.loads((ROOT/"research/reference-macros.json").read_text()):
            self.assertEqual(encode_macro(v["spec"]).hex(),v["wire"])
    def test_default_dpi_layout_and_selective_mask(self):
        packets=plan(self.config,['dpi']);self.assertEqual(len(packets),1)
        p=packets[0];self.assertEqual(p.header[6],1)
        self.assertEqual(struct.unpack_from('<6H',p.payload,9),(400,800,1000,1200,1600,3200))
        self.assertEqual(p.payload[9:25],p.payload[25:41]);self.assertEqual(p.payload[4],6)
    def test_known_default_mouse_mapping(self):
        p=plan(self.config,['buttons'])[0]
        self.assertEqual(p.payload[128:152].hex(),'f0000002f1000002f2000002f4000002f30000020300000b')
    def test_invalid_dpi_rejected(self):
        for dpi in ([0],[201],[13000],[],[800]*7,[True]):
            self.config['dpi']=dpi
            with self.assertRaises(ValueError):plan(self.config)
    def test_left_click_required(self):
        self.config['buttons']['left']='disabled'
        with self.assertRaises(ValueError):plan(self.config)
    def test_unknown_field_rejected(self):
        self.config['polling_hzz']=1000
        with self.assertRaises(ValueError):plan(self.config)
    def test_macro_layout_short_and_extended_delay(self):
        spec={'slot':0,'repeat':2,'events':[{'key':4,'action':'down','delay_ms':50},{'key':4,'action':'up'}]}
        self.assertEqual(encode_macro(spec)[:8],bytes.fromhex('02 00 05 04 81 04 00 00'))
        spec['events'][0]['delay_ms']=2000
        self.assertEqual(encode_macro(spec)[:12],bytes.fromhex('02 00 00 04 00 01 00 64 81 04 00 00'))
    def test_macro_stuck_key_and_overflow_rejected(self):
        for events in ([{'key':4,'action':'down'},{'key':5,'action':'down'}],
                       [{'key':4,'action':x} for _ in range(40) for x in ('down','up')]):
            with self.assertRaises(ValueError):encode_macro({'slot':0,'events':events})
    def test_actual_hardware_status(self):
        r=decode_status(bytes.fromhex('05 00 01 01 00 07 ff'))
        self.assertEqual((r['polling_hz'],r['dpi_stage'],r['lighting_mode'],r['lighting_speed']),(1000,2,'off',4))
    def test_macro_reference_must_exist(self):
        self.config['buttons']['back']={'macro':3}
        with self.assertRaises(ValueError):plan(self.config)

if __name__=='__main__': unittest.main()
