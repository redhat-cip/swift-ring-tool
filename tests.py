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

import pickle
import unittest

import mock
import xattr

from swiftringtool import ring_shift_power, get_acc_cont_obj
from swift.common.ring import builder


class RingToolTest(unittest.TestCase):
    def test_ring_shift_power(self):
        rb = builder.RingBuilder(8, 3, 1)
        rb.add_dev({'id': 0, 'zone': 0, 'weight': 1, 'ip': '127.0.0.1',
                    'port': 10000, 'device': 'sda1', 'region': 0})
        rb.add_dev({'id': 1, 'zone': 1, 'weight': 1, 'ip': '127.0.0.1',
                    'port': 10001, 'device': 'sda1', 'region': 0})
        rb.add_dev({'id': 2, 'zone': 2, 'weight': 1, 'ip': '127.0.0.1',
                    'port': 10002, 'device': 'sda1', 'region': 0})
        rb.rebalance()
        
        b = builder.RingBuilder(1, 1, 1)  # Dummy values
        b.copy_from(rb)

        ring = b.to_dict()
        new_ring = ring_shift_power(ring)
        self.assertEqual(ring.get('part_power'), 8)
        self.assertEqual(new_ring.get('part_power'), 9)
        self.assertEqual(new_ring.get('version'), 4)

    @mock.patch('__builtin__.open')
    def test_get_acc_cont_obj(self, open_mock):
        metadata = pickle.dumps({'name': '/a/c/o'})
        xattr.getxattr = mock.Mock(side_effect=[metadata, IOError])
        acc, cont, obj = get_acc_cont_obj("filename")
        self.assertEqual(acc, 'a')
        self.assertEqual(cont, 'c')
        self.assertEqual(obj, 'o')
