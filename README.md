# swift-ring-tool

swift-ring-tool is a tool to increase the partition power of an OpenStack Swift ring without the need to copy all data to a new cluster.

**Warning! By using this tool, you risk complete data loss. Test this tool in advance and make sure it works for you. **

1. **Start with an object ring**  
    This is the object ring also used in SAIO (<http://docs.openstack.org/developer/swift/development_saio.html>) with a partition power of 2 (instead of 10).

        swift-ring-builder object.builder create 2 3 1
        swift-ring-builder object.builder add r1z1-127.0.0.1:6010/sdb1 1
        swift-ring-builder object.builder add r1z2-127.0.0.1:6020/sdb2 1
        swift-ring-builder object.builder add r1z3-127.0.0.1:6030/sdb3 1
        swift-ring-builder object.builder add r1z4-127.0.0.1:6040/sdb4 1
        swift-ring-builder object.builder rebalance

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
        
        python swiftringtool.py --increase-partition-power object.builder

1. **Stop Swift cluster, copy updated ring to storage & proxy nodes**  
    Object access will fail until the next step is finished. The downtime depends on the amount of objects on each disk and disk speed.

1. **Move objects to new partitions**
    Since the partitions changed it is required to move the files to their new
    partitions. This is basically just a renaming on the same device, thus no
    heavy data movement is required in this step. It works like this:

    * Walk a given path and search for files with suffix `.data, .ts or .db`.
    * For each object file: get account, container and object name from XFS attributes.
    * For each account/container database file: get account and container database.
    * Compute partition value using given ring file.
    * Build new name by replacing old partition value with new computed value.
    * Create new directory if not existing and move file to new directory.

        python swiftringtool --move-object-files /etc/swift/object.ring.gz /srv/node/
    
1. **Restart Swift cluster**
    
    Database and object files are now on the correct partititons; however it is likely that the databases/object files are stored on 
    handoff partitions. Swift replicatores will take care of this and move data to their primary locations (this will take some time
    of course).
