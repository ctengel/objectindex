Install SeaweedFS on Fedora

```
$ sudo dnf install golang
$ sudo useradd -m seaweedfs
$ sudo su - seaweedfs
$ go install -tags 5BytesOffset github.com/seaweedfs/seaweedfs/weed@3.96
```

Issues:
- #50 - double check alignment
- #51 - commit this
- #54 - fix NUC boot issue
