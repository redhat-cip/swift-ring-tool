# swift-ring-tool

swift-ring-tool is a tool to increase the partition power of an OpenStack Swift ring without the need to copy all data to a new cluster.

**Warning! By using this tool, you risk complete data loss. I assume no liability or responsibility for using this tool. Use it for testing only.** 

1. **Start with an object ring**  
    This is the object ring also used in SAIO (<http://docs.openstack.org/developer/swift/development_saio.html>) with a partition power of 2 (instead of 10).

        swift-ring-builder object.builder create 2 3 1
        swift-ring-builder object.builder add r1z1-127.0.0.1:6010/sdb1 1
        swift-ring-builder object.builder add r1z2-127.0.0.1:6020/sdb2 1
        swift-ring-builder object.builder add r1z3-127.0.0.1:6030/sdb3 1
        swift-ring-builder object.builder add r1z4-127.0.0.1:6040/sdb4 1
        swift-ring-builder object.builder rebalance

        swift-ring-tool --show object.builder 

        Replica:        0 1 2
        -------------------------
        Partition 0:    2 3 0
        Partition 1:    1 0 3
        Partition 2:    1 2 3
        Partition 3:    1 2 0


1. **Increase partition power**  
    The partition of an object is determined by its hash. The interesting part is in `get_nodes()` in `swift/common/ring/ring.py`: 
        
        key = hash_path(account, container, obj, raw_digest=True)
        part = struct.unpack_from('>I', key)[0] >> self._part_shift  # self._part_shif = 32 - partition_power

    The keys (hash) of an object doesn't change, even when the partition power changes. The only thig that changes is the partition.
    An object assigned to partition 2 on one ring will be assigned to partition 4 OR 5 on a ring when the partition power is increased by one.
    swift-ring-tool follows this scheme in assigning devices to partitions.  
    Looking at the object below makes clear that both partitions 4 and 5 are still using devices 1, 2 and 5, thus no data has to be moved.
    The objects just need to be renamed on the same device which is very fast.
    The drawback is that the device distribution always assigns one device to two consecutive partitions. This might not be ideal in the long run, 
    thus a migration to a new ring is done later in steps 6-9.  
        
        swift-ring-tool --increase object.builder object2.builder 
        swift-ring-tool --show object2.builder 

        Replica:        0 1 2
        -------------------------
        Partition 0:    2 3 0
        Partition 1:    2 3 0
        Partition 2:    1 0 3
        Partition 3:    1 0 3
        Partition 4:    1 2 3
        Partition 5:    1 2 3
        Partition 6:    1 2 0
        Partition 7:    1 2 0

1. ** Stop Swift cluster **

1. **Copy new ring to storage & proxy nodes**  
    Object access will fail until the next step is finished. The downtime depends on the amount of objects on each disk and disk speed.

1. **Move objects to new partitions**  
    This is basically just a renaming on the same device, thus no heavy data movement is required in this step. Doing this in parallel on all storage nodes
    will take only some minutes for the whole cluster and minimizes downtime. It works like this:

    * Walk a given path and search for files with suffix `.data, .ts or .db`.
    * For each object file: get account, container and object name from XFS attributes.
    * For each account/container database file: get account and container database.

    * Compute partition value using given ring file.
    * Build new name by replacing old partition value with new computed value.
    * Print `mkdir` and `mv` commands.

        swift-ring-tool -o /etc/swift/object.ring.gz /srv/node/ > move.sh

    This will produce three lines for every object found in `move.sh`. It looks like this:

        #AUTH_aa87acbdc679492b94050594ab8cb684/l0igrf0ln2u0rnhmsk2w/000049
        mkdir -p /srv/node/sdaa1/objects/403453/8c8/627fd992d66948fed385d5b21e44a8c8
        mv /srv/node/sdaa1/objects/12607/8c8/627fd992d66948fed385d5b21e44a8c8/1354395490.07095.data /srv/node/sdaa1/objects/403453/8c8/627fd992d66948fed385d5b21e44a8c8/1354395490.07095.data

    Watch for any errors and check move script. **RECHECK. You might suffer from a severe data loss!** Execute move script.  

    The cluster can now be used with the increased partition power. However because devices are applied to two partitions in consecutive way (see example above) it
    might be a good idea to use a well-balanced, fresh distribution in the long term. Execute the following steps to migrate the current ring to a new one. This is
    optional and I'd like to get some community feedback if this is really required.

1. ** Restart Swift cluster **

1. **Create a second ring without device mapping and rebalance this ring**  
    This is effectively a fresh ring with a well-distributed device distribution. The goal is to migrate the ring from the previous steps slowly to this ring.

        swift-ring-tool --reset object2.builder fresh.builder 
        swift-ring-builder fresh.builder rebalance
        swift-ring-tool --show fresh.builder 
        Replica:        0 1 2
        -------------------------
        Partition 0:    2 1 0
        Partition 1:    3 2 0
        Partition 2:    1 3 2
        Partition 3:    0 3 1
        Partition 4:    2 3 0
        Partition 5:    1 2 3
        Partition 6:    0 1 2
        Partition 7:    0 1 3

1. **Migrate device mapping from fresh ring to ring with increased partition power**  
    This will be done in several steps. The simplest way is to do this for every replica in one step. After every migration you need to wait until the 
    replicatos moved the partitions to their intended destionation. In this case the process looks like this:

        swift-ring-tool --migrate increased.builder fresh.builder new.builder 0
        swift-ring-tool --show new.builder 
        Replica:        0 1 2
        -------------------------
        Partition 0:    2 3 0
        Partition 1:    3 3 0
        Partition 2:    1 0 3
        Partition 3:    0 0 3
        Partition 4:    2 2 3
        Partition 5:    1 2 3
        Partition 6:    0 2 0
        Partition 7:    0 2 0

    Now write the new ring files (`swift-ring-builder new.builder write_ring`), copy them to all storage and proxy nodes and wait until the replicators finished partition moving.

        swift-ring-tool --migrate new.builder fresh.builder new2.builder 1
        swift-ring-tool --show new2.builder 
        Replica:        0 1 2
        -------------------------
        Partition 0:    2 1 0
        Partition 1:    3 2 0
        Partition 2:    1 3 3
        Partition 3:    0 3 3
        Partition 4:    2 3 3
        Partition 5:    1 2 3
        Partition 6:    0 1 0
        Partition 7:    0 1 0

    And once more: write the new ring files, copy them to all storage and proxy nodes and wait until the replicators finished partition moving.

        swift-ring-tool --migrate new2.builder fresh.builder new3.builder 2
        swift-ring-tool --show new3.builder 
        Replica:        0 1 2
        -------------------------
        Partition 0:    2 1 0
        Partition 1:    3 2 0
        Partition 2:    1 3 2
        Partition 3:    0 3 1
        Partition 4:    2 3 0
        Partition 5:    1 2 3
        Partition 6:    0 1 2
        Partition 7:    0 1 3

    Please note that during migration it is very likely that two replicas will be assigned
    to the same device (see above in the example).
    You can replicate only a fraction of the partitions in every step, for example:
        
    1. Partition 0, Replica 0 - replicate
    1. Partition 0, Replica 1 - replicate
    1. Partition 0, Replica 2 - replicate
    1. Partition 1, Replica 0 - replicate
    1. Partition 1, Replica 1 - replicate
    1. Partition 1, Replica 2 - replicate
    1. ...

    This will take longer but the number of partitions with two replicas with identical
    devies will be minimized.  
    Another approach might be to increase the number of replicas before the migration and lower it ones everything is done.
