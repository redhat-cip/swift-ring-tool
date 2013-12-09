# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright (C) 2013 eNovance SAS <licensing@enovance.com>
#
# Author: Christian Schwede <christian.schwede@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import unittest

import mock
import pickle

from swiftringtool import increase_partition_power, FileMover
from swift.common.ring import builder


class RingToolTest(unittest.TestCase):
    def setUp(self):
        class DummyOptions(object):
            def __init__(self):
                self.move_object_files = True
                self.move_container_dbs = True
                self.move_account_dbs = True
                self.ringfile = "testring"
                self.path = "testdir"

        self.dummy_options = DummyOptions()

        ringbuilder = builder.RingBuilder(8, 3, 1)
        ringbuilder.add_dev({'id': 0, 'zone': 0, 'weight': 1,
                             'ip': '127.0.0.1', 'port': 10000,
                             'device': 'sda1', 'region': 0})
        ringbuilder.add_dev({'id': 1, 'zone': 1, 'weight': 1,
                             'ip': '127.0.0.1', 'port': 10001,
                             'device': 'sda1', 'region': 0})
        ringbuilder.add_dev({'id': 2, 'zone': 2, 'weight': 1,
                             'ip': '127.0.0.1', 'port': 10002,
                             'device': 'sda1', 'region': 0})
        ringbuilder.rebalance()
        self.ringbuilder = ringbuilder
        self.testring_filename = "testring"
        self.ringbuilder.get_ring().save(self.testring_filename)

    def test_increase_partition_power(self):
        dummyring_builder = builder.RingBuilder(1, 1, 1)
        dummyring_builder.copy_from(self.ringbuilder)
        ring = dummyring_builder.to_dict()

        new_ring = increase_partition_power(ring)
        self.assertEqual(ring.get('part_power'), 8)
        self.assertEqual(new_ring.get('part_power'), 9)
        self.assertEqual(new_ring.get('version'), 4)

    @mock.patch('os.walk')
    def test_filemover_start(self, mock_walk):
        # Simulate Swift storage node files
        mock_walk.return_value = [('accounts',
                                   '_dirs',
                                   ['account.db']),
                                  ('containers',
                                   '_dirs',
                                   ['container.db']),
                                  ('objects',
                                   '_dirs',
                                   ['object.data']),
                                  ]

        fm = FileMover(self.dummy_options)

        fm._move_file = mock.Mock()
        fm.start()
        fm._move_file.assert_any_call('accounts/account.db',
                                      'accounts')
        fm._move_file.assert_any_call('containers/container.db',
                                      'containers')
        fm._move_file.assert_any_call('objects/object.data',
                                      'objects')

    @mock.patch('os.makedirs')
    @mock.patch('os.rename')
    def test_move_file(self, mock_rename, mock_makedirs):
        fm = FileMover(self.dummy_options)

        with self.assertRaises(Exception):
            fm._move_file("filename", "dummy")

        fm._get_acc_cont_obj = mock.Mock()
        info = {'account': 'account',
                'container': 'container',
                'object': 'object'}
        fm._get_acc_cont_obj.return_value = info

        fm._move_file("node/objects/0/obj.data", "objects")

        mock_rename.assert_called_with('node/objects/0/obj.data',
                                       'node/objects/61/obj.data')
        mock_makedirs.assert_called_with('node/objects/61')

    @mock.patch('xattr.getxattr')
    def test_get_acc_cont_obj(self, mock_xattr):
        pickled_metadata = pickle.dumps({'name': '/account/container/object'})
        mock_xattr.side_effect = [pickled_metadata, IOError]
        fm = FileMover(self.dummy_options)

        with mock.patch('__builtin__.open') as mock_open:
            info = fm._get_acc_cont_obj("filename")
            mock_open.assert_called_with("filename")
            self.assertEqual(info.get('account'), 'account')
            self.assertEqual(info.get('container'), 'container')
            self.assertEqual(info.get('object'), 'object')
