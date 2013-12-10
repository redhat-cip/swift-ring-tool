resetswift 

dd if=/dev/urandom of=testfile bs=1k count=1k
clear

echo -e "Upload a testfile\n"
swift upload test testfile 

echo -e "\nShow old position of object in cluster\n"
swift-get-nodes /etc/swift/object.ring.gz AUTH_test test testfile

read -p ""
clear

echo -e "Current ring, pay attention to number of partitions\n"
swift-ring-builder /etc/swift/object.builder 

read -p ""
clear

echo -e "Increase partition power, write new ring - number of partitions increased\n"
python swiftringtool.py -v --increase-partition-power -r /etc/swift/object.builder
swift-ring-builder /etc/swift/object.builder 
swift-ring-builder /etc/swift/object.builder write_ring

read -p ""
clear

echo -e "Show new position of object in cluster\n"
swift-get-nodes /etc/swift/object.ring.gz AUTH_test test testfile

read -p ""
clear

echo -e "Try to download previous object, will fail\n"
swift download test testfile

read -p ""
clear

echo -e "Move object files to their new position\n"
python swiftringtool.py -v --move-object-files -r /etc/swift/object.ring.gz -p /mnt/swift-disk/

read -p ""
clear

swift download test testfile
