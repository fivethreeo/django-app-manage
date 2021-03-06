from collections import namedtuple
import os
import shutil
import unittest

from app_manage.config import Argument
from app_manage.config import Config
from app_manage.config import DatabaseConfig
from app_manage.config import DynamicConfigError
from app_manage.config import Flag
from app_manage.config import TempDir
from app_manage.core import main
from app_manage.management.commands.registry import listen
from app_manage.utils import ensure_cleanup


Call = namedtuple('Call', 'args kwargs')


class Callback(object):
    def __init__(self):
        self._calls = []

    def __call__(self, *args, **kwargs):
        self._calls.append(Call(args, kwargs))

    @property
    def num_calls(self):
        return len(self._calls)

    def get_call(self, index):
        return self._calls[index]

    def reset(self):
        self._calls = []


class ConfigTests(unittest.TestCase):
    def test_config_default(self):
        config = Config(default=1, arg='--test', env='TEST')
        value = config.get_value([], {})
        self.assertEqual(value, 1)

    def test_config_arg(self):
        config = Config(default=1, arg='--test', env='TEST')
        value = config.get_value(['--test', 2], {})
        self.assertEqual(value, 2)

    def test_config_env(self):
        config = Config(default=1, arg='--test', env='TEST')
        value = config.get_value([], {'TEST': 3})
        self.assertEqual(value, 3)

    def test_arg_beats_env(self):
        config = Config(default=1, arg='--test', env='TEST')
        value = config.get_value(['--test', 4], {'TEST': 5})
        self.assertEqual(value, 4)

    def test_no_default(self):
        config = Config(arg='--test', env='TEST')
        self.assertRaises(
            DynamicConfigError,
            config.get_value, [], {}
        )

    def test_database_config(self):
        config = DatabaseConfig(default='sqlite:///test.sqlite')
        value = config.get_value([], {})
        self.assertEqual(value, {'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': 'test.sqlite',
            'USER': '',
            'PASSWORD': '',
            'HOST': '',
            'PORT': '',
        }})

    def test_flag(self):
        config = Config(arg=Flag('--test'))
        value = config.get_value(['--test', 1], {})
        self.assertEqual(value, True)

    def test_tempdir(self):
        config = TempDir()
        value = None
        try:
            value = config.get_value([], {})
            self.assertTrue(os.path.exists(value))
        finally:
            if value is not None:
                shutil.rmtree(value, ignore_errors=True)

    def test_argument(self):
        callback = Callback()
        argument = Argument(
            Config(
                env='CONFIG',
                arg='--config',
                default=None
            ),
            callback=callback
        )
        argument.process([], {}, {})
        self.assertEqual(callback.num_calls, 1)
        self.assertEqual(callback.get_call(0).args, ({}, None))
        callback.reset()
        argument.process(['--config', 'value'], {}, {})
        self.assertEqual(callback.num_calls, 1)
        self.assertEqual(callback.get_call(0).args, ({}, 'value'))
        callback.reset()
        argument.process([], {'CONFIG': 'value'}, {})
        self.assertEqual(callback.num_calls, 1)
        self.assertEqual(callback.get_call(0).args, ({}, 'value'))

    def test_argument_process(self):
        def callback(settings, value):
            settings['TEST'] = value
        argument = Argument(
            Config(
                env='CONFIG',
                arg='--config',
                default=None
            ),
            callback=callback
        )
        test_settings = {}
        argument.process([], {}, test_settings)
        self.assertEqual(test_settings, {'TEST': None})
        test_settings = {}
        argument.process(['--config', 'value'], {}, test_settings)
        self.assertEqual(test_settings, {'TEST': 'value'})
        test_settings = {}
        argument.process([], {'CONFIG': 'value'}, test_settings)
        self.assertEqual(test_settings, {'TEST': 'value'})


class CoreTests(unittest.TestCase):
    def tearDown(self):
        from django.conf import empty
        from django.conf import settings
        settings._wrapped = empty

    def test_main_default(self):
        with listen() as registry:
            main(['app_manage'], argv=['manage.py', 'app_manage_test'])
            self.assertEqual(registry, [
                (
                    (),
                    {
                        'settings': None,
                        'verbosity': '1',
                        'pythonpath': None,
                        'no_color': False,
                        'traceback': None,
                        'my_flag': 'flag-no-set'
                    }
                )
            ])

    def test_main_django_flag(self):
        with listen() as registry:
            main(
                ['app_manage'],
                argv=['manage.py', 'app_manage_test', '-v', '3']
            )
            self.assertEqual(registry, [
                (
                    (),
                    {
                        'settings': None,
                        'verbosity': '3',
                        'pythonpath': None,
                        'no_color': False,
                        'traceback': None,
                        'my_flag': 'flag-no-set'
                    }
                )
            ])

    def test_main_command_flag(self):
        with listen() as registry:
            main(
                ['app_manage'],
                argv=['manage.py', 'app_manage_test', '--my-flag', 'value']
            )
            self.assertEqual(registry, [
                (
                    (),
                    {
                        'settings': None,
                        'verbosity': '1',
                        'pythonpath': None,
                        'no_color': False,
                        'traceback': None,
                        'my_flag': 'value'
                    }
                )
            ])

    def test_main_arg(self):
        with listen() as registry:
            main(
                ['app_manage'],
                argv=['manage.py', 'app_manage_test', 'arg']
            )
            self.assertEqual(registry, [
                (
                    ('arg', ),
                    {
                        'settings': None,
                        'verbosity': '1',
                        'pythonpath': None,
                        'no_color': False,
                        'traceback': None,
                        'my_flag': 'flag-no-set'
                    }
                )
            ])

    def test_main_config(self):
        with listen() as registry:
            main(
                ['app_manage'],
                argv=['manage.py', 'app_manage_test', '--config', 'myvalue'],
                TEST_SETTING=Config(arg='--config', default=None)
            )
            from django.conf import settings
            self.assertEqual(settings.TEST_SETTING, 'myvalue')
            self.assertEqual(registry, [
                (
                    (),
                    {
                        'settings': None,
                        'verbosity': '1',
                        'pythonpath': None,
                        'no_color': False,
                        'traceback': None,
                        'my_flag': 'flag-no-set'
                    }
                )
            ])


class UtilsTests(unittest.TestCase):
    def test_ensure_cleanup(self):
        test_list = []
        with ensure_cleanup() as cleanup:
            if hasattr(list, 'clear'):
                cleanup.append(test_list.clear)
            else:
                def clear():
                    del test_list[:]
                cleanup.append(clear)
            test_list.append(1)
            self.assertIn(1, test_list)
        self.assertNotIn(1, test_list)
        self.assertEqual(len(test_list), 0)

    def test_ensure_cleanup_failing_cleanup(self):
        def fail_cleanup():
            raise Exception()

        with ensure_cleanup() as cleanup:
            cleanup.append(fail_cleanup)


if __name__ == '__main__':
    unittest.main()
