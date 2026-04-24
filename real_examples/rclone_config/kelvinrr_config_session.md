This is example output of running the rclone configuration. Anywhere with now input was defaulted (i.e. press enter with empty string). 


```bash 
(base) local:~ user$ rclone config
Current remotes:

Name                 Type
====                 ====

e) Edit existing remote
n) New remote
d) Delete remote
r) Rename remote
c) Copy remote
s) Set configuration password
q) Quit config
e/n/d/r/c/s/q> n
name> remote
Type of storage to configure.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / 1Fichier
   \ "fichier"
 2 / Alias for an existing remote
   \ "alias"
 3 / Amazon Drive
   \ "amazon cloud drive"
 4 / Amazon S3 Compliant Storage Providers including AWS, Alibaba, Ceph, Digital Ocean, Dreamhost, IBM COS, Minio, and Tencent COS
   \ "s3"
 5 / Backblaze B2
   \ "b2"
 6 / Box
   \ "box"
 7 / Cache a remote
   \ "cache"
 8 / Citrix Sharefile
   \ "sharefile"
 9 / Compress a remote
   \ "compress"
10 / Dropbox
   \ "dropbox"
11 / Encrypt/Decrypt a remote
   \ "crypt"
12 / Enterprise File Fabric
   \ "filefabric"
13 / FTP Connection
   \ "ftp"
14 / Google Cloud Storage (this is not Google Drive)
   \ "google cloud storage"
15 / Google Drive
   \ "drive"
16 / Google Photos
   \ "google photos"
17 / Hadoop distributed file system
   \ "hdfs"
18 / Hubic
   \ "hubic"
19 / In memory object storage system.
   \ "memory"
20 / Jottacloud
   \ "jottacloud"
21 / Koofr
   \ "koofr"
22 / Local Disk
   \ "local"
23 / Mail.ru Cloud
   \ "mailru"
24 / Mega
   \ "mega"
25 / Microsoft Azure Blob Storage
   \ "azureblob"
26 / Microsoft OneDrive
   \ "onedrive"
27 / OpenDrive
   \ "opendrive"
28 / OpenStack Swift (Rackspace Cloud Files, Memset Memstore, OVH)
   \ "swift"
29 / Pcloud
   \ "pcloud"
30 / Put.io
   \ "putio"
31 / QingCloud Object Storage
   \ "qingstor"
32 / SSH/SFTP Connection
   \ "sftp"
33 / Sugarsync
   \ "sugarsync"
34 / Tardigrade Decentralized Cloud Storage
   \ "tardigrade"
35 / Transparently chunk/split large files
   \ "chunker"
36 / Union merges the contents of several upstream fs
   \ "union"
37 / Webdav
   \ "webdav"
38 / Yandex Disk
   \ "yandex"
39 / Zoho
   \ "zoho"
40 / http Connection
   \ "http"
41 / premiumize.me
   \ "premiumizeme"
42 / seafile
   \ "seafile"
Storage> 4
** See help for s3 backend at: https://rclone.org/s3/ **

Choose your S3 provider.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / Amazon Web Services (AWS) S3
   \ "AWS"
 2 / Alibaba Cloud Object Storage System (OSS) formerly Aliyun
   \ "Alibaba"
 3 / Ceph Object Storage
   \ "Ceph"
 4 / Digital Ocean Spaces
   \ "DigitalOcean"
 5 / Dreamhost DreamObjects
   \ "Dreamhost"
 6 / IBM COS S3
   \ "IBMCOS"
 7 / Minio Object Storage
   \ "Minio"
 8 / Netease Object Storage (NOS)
   \ "Netease"
 9 / Scaleway Object Storage
   \ "Scaleway"
10 / StackPath Object Storage
   \ "StackPath"
11 / Tencent Cloud Object Storage (COS)
   \ "TencentCOS"
12 / Wasabi Object Storage
   \ "Wasabi"
13 / Any other S3 compatible provider
   \ "Other"
provider> 1
Get AWS credentials from runtime (environment variables or EC2/ECS meta data if no env vars).
Only applies if access_key_id and secret_access_key is blank.
Enter a boolean value (true or false). Press Enter for the default ("false").
Choose a number from below, or type in your own value
 1 / Enter AWS credentials in the next step
   \ "false"
 2 / Get AWS credentials from the environment (env vars or IAM)
   \ "true"
env_auth>
AWS Access Key ID.
Leave blank for anonymous access or runtime credentials.
Enter a string value. Press Enter for the default ("").
access_key_id>
AWS Secret Access Key (password)
Leave blank for anonymous access or runtime credentials.
Enter a string value. Press Enter for the default ("").
secret_access_key>
Region to connect to.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
   / The default endpoint - a good choice if you are unsure.
 1 | US Region, Northern Virginia, or Pacific Northwest.
   | Leave location constraint empty.
   \ "us-east-1"
   / US East (Ohio) Region
 2 | Needs location constraint us-east-2.
   \ "us-east-2"
   / US West (Northern California) Region
 3 | Needs location constraint us-west-1.
   \ "us-west-1"
   / US West (Oregon) Region
 4 | Needs location constraint us-west-2.
   \ "us-west-2"
   / Canada (Central) Region
 5 | Needs location constraint ca-central-1.
   \ "ca-central-1"
   / EU (Ireland) Region
 6 | Needs location constraint EU or eu-west-1.
   \ "eu-west-1"
   / EU (London) Region
 7 | Needs location constraint eu-west-2.
   \ "eu-west-2"
   / EU (Paris) Region
 8 | Needs location constraint eu-west-3.
   \ "eu-west-3"
   / EU (Stockholm) Region
 9 | Needs location constraint eu-north-1.
   \ "eu-north-1"
   / EU (Milan) Region
10 | Needs location constraint eu-south-1.
   \ "eu-south-1"
   / EU (Frankfurt) Region
11 | Needs location constraint eu-central-1.
   \ "eu-central-1"
   / Asia Pacific (Singapore) Region
12 | Needs location constraint ap-southeast-1.
   \ "ap-southeast-1"
   / Asia Pacific (Sydney) Region
13 | Needs location constraint ap-southeast-2.
   \ "ap-southeast-2"
   / Asia Pacific (Tokyo) Region
14 | Needs location constraint ap-northeast-1.
   \ "ap-northeast-1"
   / Asia Pacific (Seoul)
15 | Needs location constraint ap-northeast-2.
   \ "ap-northeast-2"
   / Asia Pacific (Osaka-Local)
16 | Needs location constraint ap-northeast-3.
   \ "ap-northeast-3"
   / Asia Pacific (Mumbai)
17 | Needs location constraint ap-south-1.
   \ "ap-south-1"
   / Asia Pacific (Hong Kong) Region
18 | Needs location constraint ap-east-1.
   \ "ap-east-1"
   / South America (Sao Paulo) Region
19 | Needs location constraint sa-east-1.
   \ "sa-east-1"
   / Middle East (Bahrain) Region
20 | Needs location constraint me-south-1.
   \ "me-south-1"
   / Africa (Cape Town) Region
21 | Needs location constraint af-south-1.
   \ "af-south-1"
   / China (Beijing) Region
22 | Needs location constraint cn-north-1.
   \ "cn-north-1"
   / China (Ningxia) Region
23 | Needs location constraint cn-northwest-1.
   \ "cn-northwest-1"
   / AWS GovCloud (US-East) Region
24 | Needs location constraint us-gov-east-1.
   \ "us-gov-east-1"
   / AWS GovCloud (US) Region
25 | Needs location constraint us-gov-west-1.
   \ "us-gov-west-1"
region> 4
Endpoint for S3 API.
Leave blank if using AWS to use the default endpoint for the region.
Enter a string value. Press Enter for the default ("").
endpoint>
Location constraint - must be set to match the Region.
Used when creating buckets only.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / Empty for US Region, Northern Virginia, or Pacific Northwest.
   \ ""
 2 / US East (Ohio) Region.
   \ "us-east-2"
 3 / US West (Northern California) Region.
   \ "us-west-1"
 4 / US West (Oregon) Region.
   \ "us-west-2"
 5 / Canada (Central) Region.
   \ "ca-central-1"
 6 / EU (Ireland) Region.
   \ "eu-west-1"
 7 / EU (London) Region.
   \ "eu-west-2"
 8 / EU (Paris) Region.
   \ "eu-west-3"
 9 / EU (Stockholm) Region.
   \ "eu-north-1"
10 / EU (Milan) Region.
   \ "eu-south-1"
11 / EU Region.
   \ "EU"
12 / Asia Pacific (Singapore) Region.
   \ "ap-southeast-1"
13 / Asia Pacific (Sydney) Region.
   \ "ap-southeast-2"
14 / Asia Pacific (Tokyo) Region.
   \ "ap-northeast-1"
15 / Asia Pacific (Seoul) Region.
   \ "ap-northeast-2"
16 / Asia Pacific (Osaka-Local) Region.
   \ "ap-northeast-3"
17 / Asia Pacific (Mumbai) Region.
   \ "ap-south-1"
18 / Asia Pacific (Hong Kong) Region.
   \ "ap-east-1"
19 / South America (Sao Paulo) Region.
   \ "sa-east-1"
20 / Middle East (Bahrain) Region.
   \ "me-south-1"
21 / Africa (Cape Town) Region.
   \ "af-south-1"
22 / China (Beijing) Region
   \ "cn-north-1"
23 / China (Ningxia) Region.
   \ "cn-northwest-1"
24 / AWS GovCloud (US-East) Region.
   \ "us-gov-east-1"
25 / AWS GovCloud (US) Region.
   \ "us-gov-west-1"
location_constraint> 4
Canned ACL used when creating buckets and storing or copying objects.

This ACL is used for creating objects and if bucket_acl isn't set, for creating buckets too.

For more info visit https://docs.aws.amazon.com/AmazonS3/latest/dev/acl-overview.html#canned-acl

Note that this ACL is applied when server-side copying objects as S3
doesn't copy the ACL from the source but rather writes a fresh one.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / Owner gets FULL_CONTROL. No one else has access rights (default).
   \ "private"
 2 / Owner gets FULL_CONTROL. The AllUsers group gets READ access.
   \ "public-read"
   / Owner gets FULL_CONTROL. The AllUsers group gets READ and WRITE access.
 3 | Granting this on a bucket is generally not recommended.
   \ "public-read-write"
 4 / Owner gets FULL_CONTROL. The AuthenticatedUsers group gets READ access.
   \ "authenticated-read"
   / Object owner gets FULL_CONTROL. Bucket owner gets READ access.
 5 | If you specify this canned ACL when creating a bucket, Amazon S3 ignores it.
   \ "bucket-owner-read"
   / Both the object owner and the bucket owner get FULL_CONTROL over the object.
 6 | If you specify this canned ACL when creating a bucket, Amazon S3 ignores it.
   \ "bucket-owner-full-control"
acl>
The server-side encryption algorithm used when storing this object in S3.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / None
   \ ""
 2 / AES256
   \ "AES256"
 3 / aws:kms
   \ "aws:kms"
server_side_encryption>
If using KMS ID you must provide the ARN of Key.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / None
   \ ""
 2 / arn:aws:kms:*
   \ "arn:aws:kms:us-east-1:*"
sse_kms_key_id>
The storage class to use when storing new objects in S3.
Enter a string value. Press Enter for the default ("").
Choose a number from below, or type in your own value
 1 / Default
   \ ""
 2 / Standard storage class
   \ "STANDARD"
 3 / Reduced redundancy storage class
   \ "REDUCED_REDUNDANCY"
 4 / Standard Infrequent Access storage class
   \ "STANDARD_IA"
 5 / One Zone Infrequent Access storage class
   \ "ONEZONE_IA"
 6 / Glacier storage class
   \ "GLACIER"
 7 / Glacier Deep Archive storage class
   \ "DEEP_ARCHIVE"
 8 / Intelligent-Tiering storage class
   \ "INTELLIGENT_TIERING"
storage_class>
Edit advanced config? (y/n)
y) Yes
n) No (default)
y/n> n
Remote config
--------------------
[s3public]
type = s3
provider = AWS
region = us-west-2
location_constraint = us-west-2
--------------------
y) Yes this is OK (default)
e) Edit this remote
d) Delete this remote
y/e/d> y
Current remotes:

Name                 Type
====                 ====
ftp                  ftp
http                 http
public               s3
remote               s3
s3public             s3

e) Edit existing remote
n) New remote
d) Delete remote
r) Rename remote
c) Copy remote
s) Set configuration password
q) Quit config
e/n/d/r/c/s/q> q
```