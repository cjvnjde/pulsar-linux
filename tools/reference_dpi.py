"""Audit absolute DPI encoding against QML and x86 code in the original EXE.

Analysis dependencies: Node.js, pefile, unicorn, and the extracted vendor EXE.
No vendor executable is launched and no USB operations are executed.
Fixtures generated here can be checked without these dependencies.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

from reference_packets import PE, ROOT, capture, convert_parameter1

RESOURCE_TABLES = ((0x42f8e0, 0x42f9a0, 0x42fae0),
                   (0x4332e0, 0x433460, 0x4337a0),
                   (0x441840, 0x442440, 0x443ac0))


def qml_from_executable():
    """Read these two resources directly from the PE's Qt resource tables."""
    mem = PE.get_memory_mapped_image()
    base = PE.OPTIONAL_HEADER.ImageBase
    wanted = {'modules/qml/main.qml', 'modules/qml/J2/DpiSetting.qml'}
    result = {}
    for tree, names, data in RESOURCE_TABLES:
        def walk(index, path=''):
            pos = tree - base + index * 14
            name_offset, flags = struct.unpack_from('>IH', mem, pos)
            name_pos = names - base + name_offset
            size = struct.unpack_from('>H', mem, name_pos)[0]
            name = mem[name_pos + 6:name_pos + 6 + size * 2].decode('utf-16-be') if index else ''
            path = '/'.join(p for p in (path, name) if p)
            if flags & 2:
                count, start = struct.unpack_from('>II', mem, pos + 6)
                for child in range(start, start + count):
                    walk(child, path)
            elif path in wanted:
                offset = data - base + struct.unpack_from('>I', mem, pos + 10)[0]
                size = struct.unpack_from('>I', mem, offset)[0]
                blob = mem[offset + 4:offset + 4 + size]
                result[path] = (zlib.decompress(blob[4:]) if flags & 1 else blob).decode('utf-8')
        walk(0)
    if set(result) != wanted:
        raise RuntimeError('Expected DPI QML resources not found in original EXE')
    return result


def qml_function(source, name):
    match = re.search(r'    function ' + re.escape(name) + r'\([^)]*\)\s*\{.*?\n    \}', source, re.S)
    if not match:
        raise RuntimeError(f'Original QML function {name} not found')
    return match.group().strip()


NODE_RUNNER = r'''
const vm = require('node:vm');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = input.vectors.map(vector => {
    const stage = {root: {currentDpiCount: vector.dpi.length},
                   ui_View: {setDataList() {}, setData() {}}};
    vector.dpi.concat([2000,2000]).forEach((value,index) => {
        stage[`dpi${index}TXT`] = {text:String(value)};
    });
    vm.createContext(stage);
    vm.runInContext(input.saveDpi,stage);
    let payload;
    const main = {
        dpiSettingMain: {currentDpiCount: vector.dpi.length,
                         saveData: () => stage.saveData()},
        lightControlMain: {saveData: () => vector.colors},
        keyMatrixMain: {modKeys: {saveData: () => input.keys.flat()}},
        ui_View: {mouseSetParameter_1: (bytes,mask) => {payload = {bytes,mask};}}
    };
    vm.createContext(main);
    vm.runInContext(input.saveParameter,main);
    main.o_saveData1(vector.mask);
    if (payload.bytes.length !== 192) throw Error('Original QML payload size');
    return payload;
});
process.stdout.write(JSON.stringify(results));
'''


def main():
    qml = qml_from_executable()
    default = json.loads((ROOT / 'pulsar3/data/default.json').read_text())
    keys = [[0,0,240,0],[0,0,241,0],[0,0,242,0],[0,0,244,0],[0,0,243,0],
            [5,0,3,0],[5,0,2,0],[5,0,4,0]] + [[0,0,0,0]] * 6 + [[255,0,1,0],[255,0,2,0]]
    values = {'defaults': [400,800,1000,1200,1600,3200],
              'all_200': [200] * 6,
              'only_last_3200': [200,200,200,200,200,3200],
              'higher_maximum': [400,800,1000,1200,1600,12000],
              'user_test': [400,800,1500,3000,6000,12000],
              'boundaries': [200,300,400,11800,11900,12000]}
    colors = list(bytes.fromhex(''.join(c[1:] for c in default['lighting']['colors'])))
    vectors = [{'name': name, 'dpi': dpi, 'mask': mask, 'colors': colors}
               for name, dpi in values.items() for mask in (1, 7)]
    request = {'vectors': vectors, 'keys': keys,
               'saveDpi': qml_function(qml['modules/qml/J2/DpiSetting.qml'], 'saveData'),
               'saveParameter': qml_function(qml['modules/qml/main.qml'], 'o_saveData1')}
    result = subprocess.run(['node', '-e', NODE_RUNNER], input=json.dumps(request),
                            capture_output=True, text=True, check=True)
    fixtures = []
    for vector, ui in zip(vectors, json.loads(result.stdout), strict=True):
        converted = convert_parameter1(ui['bytes'])
        original = capture(0x405860, ('data', ui['mask']), converted)
        config = deepcopy(default); config['dpi'] = vector['dpi']
        sections = ['dpi'] if vector['mask'] == 1 else ['dpi', 'colors', 'buttons']
        fixtures.append({'name': vector['name'], 'config': config, 'sections': sections,
                         'header': original['header'], 'payload': original['payload']})
        words = struct.unpack_from('<8H', bytes.fromhex(original['payload']), 9)
        if words[:6] != tuple(vector['dpi']):
            raise RuntimeError(f'Original DPI encoding differs: {words}')
        print(vector['name'], 'mask', vector['mask'], 'DPI words', words)
    exe = ROOT / 'research/extracted/app/HATOR_Pulsar3_Software.exe'
    out = {'exe_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
           'source': 'Embedded DpiSetting.saveData and main.o_saveData1; original x86 0x412de2..0x412e8e and 0x405860, stopped before 0x404e80 USB sender.',
           'vectors': fixtures}
    (ROOT / 'research/reference-dpi.json').write_text(json.dumps(out, indent=2) + '\n')


if __name__ == '__main__':
    main()
