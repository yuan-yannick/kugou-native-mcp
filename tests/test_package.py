import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from kugou_native_mcp import __version__
from kugou_native_mcp.configuration import TOOLS,install,uninstall,make_block
from kugou_native_mcp.installation import find_executable,is_client_path

class ConfigurationTests(unittest.TestCase):
    def test_register_preserve_and_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config.toml'
            before='model = "example"\n[mcp_servers.other]\ncommand = "other.exe"\n'
            p.write_text(before,'utf-8')
            install(p,python=sys.executable,port=9444)
            actual=tomllib.loads(p.read_text('utf-8'))
            self.assertEqual(actual['mcp_servers']['other']['command'],'other.exe')
            self.assertEqual(actual['mcp_servers']['kugou-native']['enabled_tools'],TOOLS)
            self.assertEqual(actual['mcp_servers']['kugou-native']['env']['KUGOU_CDP_PORT'],'9444')
            self.assertTrue(list(p.parent.glob('config.toml.backup-*')))
            with self.assertRaises(RuntimeError):install(p)
            uninstall(p)
            self.assertEqual(tomllib.loads(p.read_text('utf-8')),tomllib.loads(before))

    def test_register_empty_config(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config.toml'
            install(p);uninstall(p)
            self.assertEqual(tomllib.loads(p.read_text('utf-8')),{})

    def test_refuse_tampered_management_block(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'config.toml'
            p.write_text(make_block()+'\n','utf-8')
            original=p.read_text('utf-8').replace('# END kugou-native-mcp managed',
                '[mcp_servers.unrelated]\ncommand="keep"\n# END kugou-native-mcp managed')
            p.write_text(original,'utf-8')
            with self.assertRaises(RuntimeError):uninstall(p)
            self.assertEqual(p.read_text('utf-8'),original)

    def test_executable_and_unicode_path(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'客户端目录/KuGou.exe';p.parent.mkdir();p.write_bytes(b'test-only')
            self.assertEqual(find_executable(p),p.resolve())
            with patch.dict('os.environ',{'KUGOU_EXE_PATH':str(p)}):
                self.assertTrue(is_client_path(str(p)))
                self.assertFalse(is_client_path(str(p.with_name('other.exe'))))
            block=tomllib.loads(make_block(exe=p))
            self.assertEqual(Path(block['mcp_servers']['kugou-native']['env']['KUGOU_EXE_PATH']),p.resolve())

class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_resources_and_invalid_inputs(self):
        from kugou_native_mcp.server import mcp,BRIDGE
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.assertIn('playFavorites',BRIDGE)
        self.assertEqual(len(await mcp.list_tools()),10)
        # Source/isolated-wheel tests need the same import path in the server child.
        env={'PYTHONPATH':os.environ['PYTHONPATH']} if os.environ.get('PYTHONPATH') else None
        params=StdioServerParameters(command=sys.executable,args=['-m','kugou_native_mcp','serve'],env=env)
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                self.assertEqual({t.name for t in (await session.list_tools()).tools},set(TOOLS))
                for name,args in [
                    ('kugou_play_favorites',{'start_index':0}),
                    ('kugou_play_favorites',{'mode':'unsupported'}),
                    ('kugou_get_favorites',{'limit':201}),
                    ('kugou_get_favorites',{'collection_name':' '}),
                ]:
                    self.assertTrue((await session.call_tool(name,args)).isError)

if __name__=='__main__':unittest.main()
