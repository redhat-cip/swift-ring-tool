# swift-ring-tool

swift-ring-tool is a tool to increase the partition power of an OpenStack Swift ring without the need to copy all data to a new cluster.

**Warning! By using this tool, you risk complete data loss. Test this tool in advance and make sure it works for you.**

1. **Increasing the partition power**  
    The partition of an object is determined by its hash. The interesting part is in `get_nodes()` in `swift/common/ring/ring.py`: 
        
        key = hash_path(account, container, obj, raw_digest=True)
        part = struct.unpack_from('>I', key)[0] >> self._part_shift  # self._part_shif = 32 - partition_power

    The keys (hash) of an object doesn't change, even when the partition power changes. The only thig that changes is the partition.

    You can test this with swift-get-nodes:

        swift-get-nodes /etc/swift/object.ring.gz account container object
        [...]
        Partition   988
        Hash        3dc84eca83ff53e200ed3268b3ace9c2
        [...]
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb4/objects/988/9c2/3dc84eca83ff53e200ed3268b3ace9c2/"
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb2/objects/988/9c2/3dc84eca83ff53e200ed3268b3ace9c2/"
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb3/objects/988/9c2/3dc84eca83ff53e200ed3268b3ace9c2/"
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb1/objects/988/9c2/3dc84eca83ff53e200ed3268b3ace9c2/" # [Handoff]
        
    After increasing the partition power the partition changes, but not the hash itself:
        
        python swiftringtool.py  --increase-partition-power -r /etc/swift/object.builder 
        swift-ring-builder /etc/swift/object.builder write_ring
        swift-get-nodes /etc/swift/object.ring.gz account container object
        [...]
        Partition   1977
        Hash        3dc84eca83ff53e200ed3268b3ace9c2
        [...]
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb4/objects/1977/9c2/3dc84eca83ff53e200ed3268b3ace9c2/"
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb2/objects/1977/9c2/3dc84eca83ff53e200ed3268b3ace9c2/"
        ssh 127.0.0.1 "ls -lah ${DEVICE:-/srv/node}/sdb3/objects/1977/9c2/3dc84eca83ff53e200ed3268b3ace9c2/"

    An object assigned to partition 2 on one ring will be assigned to partition 4 OR 5 on a ring when the partition power is increased by one.
    swift-ring-tool follows this scheme in assigning devices to partitions; the objects just need to be renamed on the same device which is very fast.
        
1. **Move objects to new partitions**
    
    Just increasing the partition power of the ring and deploying this ring to the proxy & storage servers is just half the way.
    Since the partitions changed it is required to move the files to their new partitions. This is basically just a renaming on 
    the same device, thus no heavy data movement is required in this step. It works like this:

    1. Walk a given path and search for files with suffix `.data, .ts or .db`
    1. For each object file: get account, container and object name from XFS attributes
    1. For each account/container database file: get account and container name
    1. Compute partition value using given ring file
    1. Build new name by replacing old partition value with new computed value
    1. Create new directory if not existing and move file to new directory

    To move files to their new partition, do the following on all storage nodes (most likely in parallel):

    1. Stop all services on the Swift cluster
    1. Copy updated ring to storage & proxy nodes
    1. Move all files on storage nodes (using `python swiftringtool.py --move-\*`)
    1. Restart Swift cluster
    
    Database and object files are now on the correct partititons; however it is likely that the databases/object files are stored on 
    handoff partitions. Swift replicators will take care of this and move data to their primary locations (this will take some time
    of course).
