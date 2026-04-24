# Backblaze B2 via rclone cheatsheet

- [Create B2 remote](#create-b2-remote)
- [Tasks](#tasks)
	- [List buckets](#list-buckets)
	- [Synchronize local files to bucket](#synchronize-local-files-to-bucket)
	- [Synchronize local files to bucket - checksum](#synchronize-local-files-to-bucket---checksum)
	- [Verify local files against bucket](#verify-local-files-against-bucket)
- [Reference](#reference)

## Create B2 remote

- Where "Key ID" is `account`.
- Where "Application key" is `key`.
- Using `b2` as the remote name and used in all task examples (e.g. as `b2:`).

```sh
$ rclone config

# n) New remote

# name: b2

#XX / Backblaze B2
#   \ "b2"

# Account ID or Application Key ID
# Enter a string value. Press Enter for the default ("").
# account> 

# Application Key
# Enter a string value. Press Enter for the default ("").
# key> 
```

All done, confirm settings:

```sh
$ cat ~/.config/rclone/rclone.conf

[b2]
type = b2
account = KEY_ID
key = APPLICATION_KEY
hard_delete = true
```

## Tasks

### List buckets

```sh
$ rclone lsd b2:

# -1 2019-08-27 23:02:27        -1 BUCKET_01
# -1 2019-08-27 23:02:27        -1 BUCKET_02
# -1 2019-08-27 23:02:27        -1 BUCKET_03
```

### Synchronize local files to bucket

Will perform the following:

- Push all files from `/path/to/local/source` to target bucket `BUCKET_NAME`.
- Files found in target bucket not in source will be deleted.
- Files considered identical if **file size and modification date** match.
- Progress displayed to terminal, output sent to `/path/to/rclone.log`.
- Using [`--fast-list`](https://rclone.org/b2/#fast-list) to action `rclone` to pull all current target bucket files in a single/minimal number of API calls. Based on the number of target bucket files to consider this may have positive/negative execution time/cost benefit.
- Use [`--transfers`](https://rclone.org/docs/#transfers-n) to control number of parallel file transfers to target bucket, tune based on available upstream bandwidth.

```sh
$ rclone sync \
  --fast-list \
  --log-file /path/to/rclone.log \
  --progress \
  --stats-one-line \
  --transfers 32 \
  --verbose \
    /path/to/local/source \
    b2:BUCKET_NAME
```

### Synchronize local files to bucket - checksum

- Identical to [Synchronize local files to bucket](#synchronize-local-files-to-bucket), but using [`--checksum`](https://rclone.org/docs/#c-checksum) flag means files considered identical if **file size and SHA-1** match.
- A more thorough synchronization, but will take longer to execute as `rclone` must calculate SHA-1 checksums for _every_ source file - B2 keeps a SHA-1 checksum for every target bucket file, so no additional overhead there. 

```sh
$ rclone sync \
  --checksum \
  --fast-list \
  --log-file /path/to/rclone.log \
  --progress \
  --stats-one-line \
  --transfers 32 \
  --verbose \
    /path/to/local/source \
    b2:BUCKET_NAME
```

### Verify local files against bucket

Will perform the following:

- Verify all files at `/path/to/local/source` against target bucket `BUCKET_NAME`.
- Files considered identical if **file size and SHA-1** match.
- To speed up the check, provide the [`--size-only`](https://rclone.org/docs/#size-only) flag, which will consider files identical if only **file sizes** match.
- Progress displayed to terminal, output sent to `/path/to/rclone.log`.
- Using [`--fast-list`](https://rclone.org/b2/#fast-list) to action `rclone` to pull all current target bucket files in a single/minimal number of API calls. Based on the number of target bucket files to consider this may have positive/negative execution time/cost benefit.

```sh
$ rclone check \
  --fast-list \
  --log-file /temp/rclone.log \
  --progress \
  --verbose \
    /path/to/local/source \
    b2:BUCKET_NAME
```

## Reference

- https://www.backblaze.com/b2/cloud-storage.html
- https://rclone.org/b2/
