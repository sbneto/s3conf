# s3conf

[![Build Status](https://travis-ci.org/sbneto/s3conf.svg?branch=master)](https://travis-ci.org/sbneto/s3conf)

Utility package to help managing configuration files stored in S3-like services. Needs python3.

# Installation

```python
pip install s3conf
```

# Usage

## Quick Start

### Create an Environment

Run this command in the project root:

```bash
s3conf init dev s3://my-dev-bucket/dev-env/myfile.env
```

This will create the file `s3conf.ini` if it does not exist and add the following lines to it:

```ini
[dev]
S3CONF = s3://my-dev-bucket/dev-env/myfile.env
```

### S3 Credentials

If you have a `aws-cli` working, `s3conf` will user your default credentials. This should already be 
enough to get you started.

#### Manually setting the credentials

If you do not have a configured aws-cli, the client will search for these authentication variables in
order to access the remote storage:

```bash
S3CONF_ACCESS_KEY_ID=***access_key***
S3CONF_SECRET_ACCESS_KEY=***secret_access_key***
S3CONF_S3_ENDPOINT_URL=***endpoint_url***
```

These variables map to their `AWS_` counterpart used for regular Boto3 configuration.
The client also searchs for the regular `AWS_` variables, but their `S3CONF_*` version take precedence. 
They are particularly useful when using non-aws blob storage services that are compatible with S3, 
such as DigitalOcean Spaces, without messing your AWS credentials.

### Edit your environment

Run this command in any folder of the project: 

```bash
s3conf env dev -e
```

If it is a new bucket/file, use the `-c` flag to create it:

```bash
s3conf env dev -ec
```

This will download the environment file from the S3-like storage to a temporary file, open your 
default file editor for manual editing (much like as `crontab -e` works) and upload the file back 
to the remote storage service if any edits were made.

### Retrieve your environment

Running `s3conf env dev` in any folder of the project reads and output to stdout the contents
of the environment file, while logs are sent to stderr:

```bash
$ s3conf env dev
info: Loading configs from s3://my-dev-bucket/dev-env/myfile.env
ENV_VAR_1=some_data_1
ENV_VAR_2=some_data_2
ENV_VAR_3=some_data_3
```

To apply this environment to your current shell you can do the following:

```bash
$ export $(s3conf env dev)
info: Loading configs from s3://my-dev-bucket/dev-env/myfile.env
```

### Adding a credential file to the environment

If you have some file or folder that you want to save in the environment, you can add a mapping:

```bash
s3conf add dev ./some-credentials-file-or-folder
```


### Pushing your credential files to the remote storage

```bash
s3conf push dev
```

### Retrieve your environment with file mappings

Use the `-m` flag to download the file mappings to your current project folder:

```bash
export $(s3conf env dev -m)
```

## Using With Docker

The most straight forward way to use this client with docker is to create an `entrypoint.sh` in your image 
that sets the environment variables and map all needed files:

```bash
#!/usr/bin/env bash
set -e
export $(s3conf env dev -m)
exec "$@"
```

And use it when running your container (assuming your entrypoint is in `/app/entrypoint.sh` and ***is executable***)

```bash 
docker run --entrypoint `/app/entrypoint.sh` my_image my_command 
```
