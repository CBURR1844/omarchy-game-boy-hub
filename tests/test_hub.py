import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
import zipfile

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))
spec = importlib.util.spec_from_file_location('hub', PLUGIN / 'hub.py')
hub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hub)

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base_patch = patch.object(hub, 'BASE', self.root / 'library')
        self.base_patch.start()
        self.config = {'folders': [str(self.root)], 'favorites': [], 'recent': [], 'patches': {},
                       'speed': 4, 'rewind': True, 'fullscreen': False}

    def tearDown(self):
        self.base_patch.stop()
        self.temp.cleanup()

    def test_zip_reads_actual_game_title_and_filters_non_rom_archives(self):
        with zipfile.ZipFile(self.root / 'download.zip', 'w') as z:
            z.writestr('folder/Pokemon Crystal.gbc', b'rom')
        with zipfile.ZipFile(self.root / 'documents.zip', 'w') as z:
            z.writestr('notes.txt', 'hello')
        result = hub.scan(self.config)
        self.assertEqual(len(result['games']), 1)
        self.assertEqual(result['games'][0]['title'], 'Pokemon Crystal')
        self.assertEqual(result['games'][0]['system'], 'GBC')

    def test_corrupt_and_multi_rom_archives_do_not_hide_good_games(self):
        (self.root / 'broken.zip').write_bytes(b'broken')
        (self.root / 'good.GBA').write_bytes(b'rom')
        with zipfile.ZipFile(self.root / 'collection.zip', 'w') as z:
            z.writestr('a.gba', b'a')
            z.writestr('b.gba', b'b')
        result = hub.scan(self.config)
        self.assertEqual(len(result['games']), 1)
        self.assertEqual(len(result['warnings']), 2)

    def test_overlapping_roots_are_deduplicated_and_symlinks_do_not_loop(self):
        folder = self.root / 'sub'
        folder.mkdir()
        (folder / 'game.gbc').write_bytes(b'rom')
        (folder / 'loop').symlink_to(self.root, target_is_directory=True)
        self.config['folders'].append(str(folder))
        self.assertEqual(len(hub.scan(self.config)['games']), 1)

    def test_same_name_and_patched_roms_have_separate_saves(self):
        a, b = self.root / 'a/game.gba', self.root / 'b/game.gba'
        self.assertNotEqual(hub.game_directory(a), hub.game_directory(b))
        self.assertNotEqual(hub.game_directory(a), hub.game_directory(a, self.root / 'hack.bps'))

    @patch.object(hub.shutil, 'which', return_value='/usr/bin/mgba-qt')
    def test_launch_preserves_original_and_existing_saves_and_shell_characters(self, _):
        rom = self.root / 'game $(touch sentinel);.gba'
        rom.write_bytes(b'rom')
        rom.with_suffix('.sav').write_bytes(b'old battery save')
        command = hub.launch_command(rom, self.config)
        self.assertEqual(command[-1], str(rom))
        self.assertIn('fastForwardRatio=4', command)
        self.assertIn('fastForwardHeldRatio=4', command)
        self.assertIn('rewindEnable=1', command)
        save = hub.game_directory(rom) / rom.with_suffix('.sav').name
        self.assertEqual(save.read_bytes(), b'old battery save')
        save.write_bytes(b'new progress')
        hub.launch_command(rom, self.config)
        self.assertEqual(save.read_bytes(), b'new progress')
        self.assertEqual(rom.read_bytes(), b'rom')
        self.assertFalse((self.root / 'sentinel').exists())

    def test_missing_emulator_is_actionable(self):
        with patch.object(hub.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'not installed'):
                hub.launch_command(None, self.config)

    def test_cheat_matching_rejects_wrong_region_revision_and_similar_titles(self):
        match = hub.cheat_finder.matching
        self.assertTrue(match('Pokemon - Crystal Version (USA)', 'Pokemon - Crystal Version (USA, Europe) (GameShark)'))
        self.assertFalse(match('Pokemon - Crystal Version (Japan)', 'Pokemon - Crystal Version (USA, Europe)'))
        self.assertFalse(match('Pokemon - Crystal Version (USA) (Rev 1)', 'Pokemon - Crystal Version (USA)'))
        self.assertFalse(match('Pokemon - Crystal Version (USA)', 'Pokemon - Gold Version (USA)'))

    def test_cheat_parser_preserves_multiline_and_rejects_placeholders_and_memory_handlers(self):
        text = '\n'.join(['cheats = 3', 'cheat0_desc = "Money"',
                          'cheat0_code = "010F4ED8+01424FD8+013F50D8"',
                          'cheat0_enable = true', 'cheat1_code = "01XX4ED8"',
                          'cheat2_code = "010F4ED8"', 'cheat2_handler = 1'])
        codes, skipped = hub.cheat_finder.parse_codes(text, 'GBC')
        self.assertEqual(len(codes), 1)
        self.assertEqual(skipped, 2)
        self.assertEqual(len(codes[0]['lines']), 3)
        native = hub.cheat_finder.native_text(codes)
        self.assertIn('!disabled\n# Money', native)
        reparsed, omitted = hub.cheat_finder.parse_codes(native, 'GBC')
        self.assertEqual(reparsed, codes)
        self.assertEqual(omitted, 0)

    def test_gba_codebreaker_split_halves_and_action_replay_directives(self):
        codes, skipped = hub.cheat_finder.parse_codes('cheats = 1\ncheat0_code = "82000000+0001+82000002+0002"', 'GBA')
        self.assertEqual(codes[0]['lines'], ['82000000 0001', '82000002 0002'])
        codes, skipped = hub.cheat_finder.parse_codes('cheats = 1\ncheat0_code = "12345678 12345678"', 'GBA', 'Game (USA) (Action Replay)')
        self.assertEqual(codes[0]['directives'], ['PARv3'])

    def test_import_backs_up_existing_cheats_then_preserves_emulator_edits(self):
        rom = self.root / 'game.gbc'
        savedir = hub.game_directory(rom)
        savedir.mkdir(parents=True)
        target = savedir / 'game.cheats'
        target.write_text('# Old\n010F4ED8\n')
        staged = self.root / 'staged.cheats'
        staged.write_text('!disabled\n# Money\n010F4ED8\n')
        record = {'file': str(staged), 'sha256': hub.hashlib.sha256(staged.read_bytes()).hexdigest()}
        self.config['cheatImports'] = {str(rom) + '\n': record}
        hub.apply_cheat_import(rom, '', savedir, self.config)
        self.assertEqual(target.read_bytes(), staged.read_bytes())
        backup = list(savedir.glob('*.backup-*'))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_text(), '# Old\n010F4ED8\n')
        target.write_text('# Money enabled by user\n010F4ED8\n')
        hub.apply_cheat_import(rom, '', savedir, self.config)
        self.assertIn('enabled by user', target.read_text())

    def test_hacked_rom_does_not_match_base_game_database(self):
        finder = hub.cheat_finder.Finder(self.root / 'cache')
        rom = self.root / 'hack.gba'
        rom.write_bytes(b'hack')
        with patch.object(finder, 'database', side_effect=AssertionError('Must not query base game cheats')):
            found = finder.find(rom, hub.game_info(rom), hub.game_directory(rom), hub.BASE, patched=True)
        self.assertEqual(found['candidates'], [])
        self.assertIn('ROM patch', found['notice'])

    def test_offline_lookup_still_detects_local_cheat_file(self):
        rom = self.root / 'game.gbc'
        rom.write_bytes(b'rom')
        rom.with_suffix('.cheats').write_text('# Code\n010F4ED8\n')
        finder = hub.cheat_finder.Finder(self.root / 'cache')
        with patch.object(finder, 'database', side_effect=ValueError('Offline')):
            found = finder.find(rom, hub.game_info(rom), hub.game_directory(rom), hub.BASE)
        self.assertEqual(len(found['candidates']), 1)
        self.assertEqual(found['candidates'][0]['kind'], 'local')
        self.assertEqual(found['notice'], 'Offline')

if __name__ == '__main__':
    unittest.main()
