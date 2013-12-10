# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
#!/usr/bin/env python
# Copyright (c) 2013 Christian Schwede <christian.schwede@enovance.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Tool to increase the partition power of a Swift ring """

import array
import copy
import logging
import argparse
import os
import cPickle as pickle
import sys
import xattr

from swift.common.ring import Ring

try:
    from swift.common.db import AccountBroker, ContainerBroker
except ImportError:
    from swift.account.backend import AccountBroker
    from swift.container.backend import ContainerBroker


def increase_partition_power(ring):
    """ Returns ring with partition power increased by one.

    Devices will be assigned to partitions like this:

    OLD: 0, 3, 7, 5, 2, 1, ...
    NEW: 0, 0, 3, 3, 7, 7, 5, 5, 2, 2, 1, 1, ...

    Objects have to be moved when using this ring. Please see README.md """

    ring = copy.deepcopy(ring)

    new_replica2part2dev = []
    for replica in ring['_replica2part2dev']:
        new_replica = array.array('H')
        for device in replica:
            new_replica.append(device)
            new_replica.append(device)  # append device a second time
        new_replica2part2dev.append(new_replica)
    ring['_replica2part2dev'] = new_replica2part2dev

    for device in ring['devs']:
        if device:
            device['parts'] *= 2

    new_last_part_moves = []
    for partition in ring['_last_part_moves']:
        new_last_part_moves.append(partition)
        new_last_part_moves.append(partition)
    ring['_last_part_moves'] = new_last_part_moves

    ring['part_power'] += 1
    ring['parts'] *= 2
    ring['version'] += 1

    return ring


class FileMover(object):
    def __init__(self, options, *_args, **_kwargs):
        self.ring = Ring(options.ring)
        self.path = options.path
        self.options = options

    def _get_acc_cont_obj(self, filename):
        """ Returns account, container, object from XFS object metadata """

        obj_fd = open(filename)
        metadata = ''
        key = 0
        try:
            while True:
                metadata += xattr.getxattr(
                    obj_fd, '%s%s' % ("user.swift.metadata", (key or '')))
                key += 1
        except IOError:
            pass
        obj_fd.close()
        object_name = pickle.loads(metadata).get('name')
        account = object_name.split('/')[1]
        container = object_name.split('/')[2]
        obj = '/'.join(object_name.split('/')[3:])

        return {'account': account,
                'container': container,
                'object': obj}

    def start(self):
        for root, _dirs, files in os.walk(self.path):
            if "quarantined" in root:
                continue
            for filename in files:
                fullname = os.path.join(root, filename)
                if (self.options.move_object_files is True and
                        fullname.split('.')[-1] in ["data", "ts"]):
                    self._move_file(fullname, "objects")

                if (self.options.move_container_dbs is True and
                        fullname.split('.')[-1] in ["db"] and
                        "containers" in fullname):
                    self._move_file(fullname, "containers")

                if (self.options.move_account_dbs is True and
                        fullname.split('.')[-1] in ["db"] and
                        "accounts" in fullname):
                    self._move_file(fullname, "accounts")

    def _move_file(self, filename, filetype):
        if filetype == 'accounts':
            broker = AccountBroker(filename)
            info = broker.get_info()
        elif filetype == 'containers':
            broker = ContainerBroker(filename)
            info = broker.get_info()
        elif filetype == 'objects':
            info = self._get_acc_cont_obj(filename)
        else:
            raise Exception

        acc = info.get('account')
        cont = info.get('container')
        obj = info.get('object')

        partition, _nodes = self.ring.get_nodes(acc, cont, obj)

        # replace the old partition value with the new one
        # old name like '/a/b/objects/123/c/d'
        # new name like '/a/b/objects/456/c/d'
        filename_parts = filename.split('/')
        part_pos = filename_parts.index(filetype)
        filename_parts[part_pos+1] = str(partition)
        newname = '/'.join(filename_parts)

        dst_dir = os.path.dirname(newname)
        try:
            os.makedirs(dst_dir)
            logging.info("mkdir %s" % dst_dir)
        except OSError as ex:
            logging.info("mkdir %s failed: %s" % (dst_dir, ex))

        try:
            os.rename(filename, newname)
            logging.info("moved %s -> %s" % (filename, newname))
        except OSError as ex:
            logging.warning("FAILED TO MOVE %s -> %s" % (filename, newname))


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--increase-partition-power',
        action='store_true',
        help='Increase the partition power of the given ring builder file')
    parser.add_argument(
        '--move-object-files',
        action='store_true',
        help='Move all object files on given path and move \
        to computed partition')
    parser.add_argument(
        '--move-container-dbs',
        action='store_true',
        help='Move all container databases on given path and \
        move to computed partition')
    parser.add_argument(
        '--move-account-dbs',
        action='store_true',
        help='Move all account databases on given path and \
        move to computed partition')
    parser.add_argument("-r", "--ring", action="store", type=str,
                      help="Ring builder file")
    parser.add_argument(
        "-p", "--path", action="store", type=str,
        help="Storage path of accounts, containers and objects")
    parser.add_argument("-v", "--verbose", action="store_true"),

    options = parser.parse_args(args)

    if options.verbose:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

    if options.increase_partition_power and options.ring:
        with open(options.ring) as src_ring_fd:
            src_ring = src_ring_fd.read()
            src_ring = pickle.loads(src_ring)

        dst_ring = increase_partition_power(src_ring)

        with open(options.ring, "wb") as dst_ring_fd:
            pickle.dump(dst_ring, dst_ring_fd, protocol=2)

    elif (options.move_object_files or
          options.move_container_dbs or
          options.move_account_dbs) and options.ring and options.path:

        fm = FileMover(options)
        fm.start()

    else:
        parser.print_help()


if __name__ == "__main__":
    main(sys.argv[1:])
