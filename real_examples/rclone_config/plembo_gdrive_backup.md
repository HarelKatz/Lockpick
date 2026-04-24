# Mirror backup to Google Drive with rclone
My home backup solution is simple and unsophisticated: Select parts of host filesystems (like home and configuration directories) are copied to a file server using [rsync](https://rsync.samba.org/), to later be mirrored to cloud storage using [rclone](https://rclone.org). This process has been in place for many years with the main change over time being the cloud storage used. Originally that was Google Cloud Storage, later on AWS S3. Part of the deal when you get hooked up with Google Fiber is 1 TB of free Google Drive storage.

Google Drive has been known to have relatively low transfer rates and a number of other restrictions that make it less than ideal as a backup solution. But with a little effort it may work. Here is the basic command I use to sync a given folder between my server and Google Drive (see [the doc](https://rclone.org/drive/) for configuring rclone for Google Drive).

In these examples "drive:" is the rclone remote name for my Google Drive, and "/data" is a very large volume on the home server hard disk.
```
$ export EXCLUDES=/usr/local/etc/excludes.conf
$ rclone -P --skip-links --exclude-from=${EXCLUDES} -v --fast-list sync /data/backup/mine drive:/backup/mine
```
My excludes.conf lists a number of file and directory names that I don't want to be copied with the others, like "tmp" and "Downloads". The file is kept in /usr/local/etc on the server.

```
; Exclude file for rsync job (mostly targetting home directories)
tmp/
Downloads/
.cache/
.dbus/
.gvfs/
.mozilla/
.config/google-chrome/
*/Cache/
.local/share/Trash/
lost+found/
.npm/
venv/
__pycache__/
.pylint/
.config/Code/
.vscode/
Projects/
.ssh/
.gnupg/
.config/rclone
.aws
.profile
OneDrive/
Drive/
.gradle/
.android/
```

The mirror_to_gdrive.sh script itself just combines everything above with a "for" loop. The script is run by the home server's root user.

```bash
!/usr/bin/env bash
# Mirror backup to personal (1 TB) Google Drive, using rclone
SHOST=$(hostname|cut -f1 -d.)
SVOL="/data/backup"
BUACCT="me@gmail.com"
BUDIR="backup"
SDIRS=('host1' 'host2' 'host3' 'host4')
RMTNAME="drive:"
LOGFILE="/data/logs/backup/mirror_to_gdrive.log"
TIMESTAMP=`date +%Y%m%d%H%M%S`
EXCLUDES="/usr/local/etc/excludes.conf"

echo "${TIMESTAMP} Mirror backups from ${SHOST} to ${BUACCT}" >${LOGFILE}

for SDIR in ${SDIRS[@]};
do
    rclone -P --skip-links --exclude-from=${EXCLUDES} --log-file=${LOGFILE} -v --fast-list sync ${SVOL}/${SDIR} ${RMTNAME}/${BUDIR}/${SDIR}

done

TIMESTAMP=`date +%Y%m%d%H%M%S`
echo "${TIMESTAMP} Mirroring completed" >>${LOGFILE}
```
