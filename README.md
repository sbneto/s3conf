# s3conf

[![Build Status](https://travis-ci.org/sbneto/s3conf.svg?branch=master)](https://travis-ci.org/sbneto/s3conf)

Utility package to help managing configuration files stored in S3-like services. Needs python3.

# Installation

```python
pip install s3conf
```

# Usage

## Quick Start

This package provides a command line client `s3conf` that helps us to manipulate enviroment variables.
It looks for a configuration variable named `S3CONF` that should point to a file in a S3-like bucket. Eg.:

```bash
export S3CONF=s3://mybucket/myfile.env
```

If you have a `aws-cli` working, this should already be enough to get you started.

## Environemnt Configuration

In addition to the `S3CONF` environment variable, the client will also search for these 
authentication variables if they are provided:

```bash
S3CONF_ACCESS_KEY_ID=***access_key***
S3CONF_SECRET_ACCESS_KEY=***secret_access_key***
S3CONF_S3_REGION_NAME=***region_name***
S3CONF_S3_ENDPOINT_URL=***endpoint_url***
```

These variables map to their `AWS_` counterpart used for regular Boto3 configuration.
The client also searchs for the regular `AWS_` variables, but their `S3CONF_*` version take precedence. 
They are particularly useful when using non-aws blob storage services that are compatible with S3, 
such as DigitalOcean Spaces, without messing your AWS credentials.

## Configuration Files

The client can use a configuration file `.s3conf/config` that can be located in any folder along the
current folder path. E.g.: `/usr/sbneto/.s3conf/config` will be used when inside the folder 
`/usr/sbneto/data`.

This file is an INI file as described in Pyhton's [ConfigParser](https://docs.python.org/3/library/configparser.html).
You can define multiple sections in your configuration file, as well as a `DEFAULT` one:

```ini
[DEFAULT]
S3CONF_ACCESS_KEY_ID=***access_key***
S3CONF_SECRET_ACCESS_KEY=***secret_access_key***
S3CONF_S3_REGION_NAME=***region_name***
S3CONF_S3_ENDPOINT_URL=***endpoint_url***

[dev]
S3CONF=s3://my-dev-bucket/myfile.env

[prod]
S3CONF=s3://my-prod-bucket/myfile.env
```

When a section is provided to the client, the values in the config file take precedence 
over the environemnt variables:

```bash
s3conf env dev
```

## Editing Your Config Files

A convenient way to edit the Configuration File is to use the following command:

```bash
s3conf -e
```

This will open your default file editor, much like as how `crontab -e` works. If no configuration folder
is found in the current directory path, you can use the `-c` flag to create it in the current folder
`./.s3conf/config`:

```bash
s3conf -ec
```

## Setting the Environment

Once credentials are in place, we want to get the data from the file defined in the `S3CONF` environment variable.
This can be achieved with the following command: 

```bash
$ s3conf env
ENV_VAR_1=some_data_1
ENV_VAR_2=some_data_2
ENV_VAR_3=some_data_3
```

If you are using the `S3CONF` value from a particular section in your config, you should pass it as well:

```bash
$ s3conf env dev
ENV_VAR_1=some_data_1
ENV_VAR_2=some_data_2
ENV_VAR_3=some_data_3
```

The output can be used to set the environment with `export`:

```bash
$ export $(s3conf env)
```

## Editing Your Environment File

Since editing the environment file is also common, the client provides a convenient way to manipulate it:

```bash
s3conf env -e
```

This will download the environment file to a temporary file, open your default file editor (much like as 
`crontab -e` works) and upload the file back to the blob storage service only if edits were made.

## Setting/Unsetting a singe Environment Variable

You can set a single environemnt variable for a environment file pointed in a section in the following way:

```bash
s3conf set dev ENV_VAR_1=some_data_1
```

You can remove this environment variable from your file in a similar way:

```bash
s3conf unset dev ENV_VAR_1
```

## Mapping Files

Besides setting evironment variables, we sometimes need to grab some configuration files. To do so, the
client provides very convenient way to store and download these files.

If we define a variable named `S3CONF_MAP` inside the file defined in `S3CONF`, we can tell the client
to download the files as defined in the former variable. One example of this mapping would be the following:

```bash
S3CONF_MAP=s3://my_bucket/config.file:/app/config/my.file;s3://my_bucket/etc/app_config_folder/:/etc/app_config_folder/;
```

This variable would map a single file `config.file` from our s3-like service to our local file `my.file` and
the whole subfolder structure from `s3://my_bucket/etc/app_config_folder/` would be replicated in 
`/etc/app_config_folder/`. Since s3-like services have no concept of folder, it is ***VERY IMPORTANT*** to add
the ***trailing slash*** to the S3 path when it is a folder so that the client knows it has to traverse the
directory structure.

To instruct the client to map the files in the `S3CONF_MAP` when reading from the file in `S3CONF` simply
pass the `-m` flag:

```bash
s3conf env -m
``` 

## Using With Docker

The most straight forward way to use this client with docker is to create an `entrypoint.sh` in your image 
that sets the environment variables and map all needed files:

```bash
#!/usr/bin/env bash
set -e
export $(s3conf env -m)
exec "$@"
```

And use it when running your container (assuming your entrypoint is in `/app/entrypoint.sh` and ***is executable***)

```bash 
docker run --entrypoint `/app/entrypoint.sh` my_image my_command 
```

### Even Better With Phusion Baseimage

A great base image that solves many challenges of working with docker is the Phusion Base Image, that can be found in 
<https://github.com/phusion/baseimage-docker>. It manages environment variables by creating files in 
the `/etc/container_environment` folder with the environement variable name and with its contents as the
environement variables themselves (a full description of this process can be found in 
<https://github.com/phusion/baseimage-docker#environment_variables>).

 The client has a feature that automatically creates these files based on the file read from the S3-like service.
 To do so, it is enough to run it with the `--phusion` flag. Therefore, if we wanted to map files and dump them in the Phusion
 format, we would run our client in the following way:
 
 ```bash
 s3conf env -m --phusion
 ```

The Phusion container also defines how to run scripts at container startup (an alternative for the `entrypoint.sh`, 
defined in <https://github.com/phusion/baseimage-docker#running_startup_scripts>). Since the environment configuration
is something we would like to run at the container startup quite often, it makes a lot of sense to add a script that
runs the former command when creating the container. Luckly, I have already prepared an image based on Phusion Baseimage
that has python 3.6 installed (python 3 is a requirement for the client) and has it all alredy configured. It can
be found in [sbneto/phusion-python:3.6-env](https://hub.docker.com/r/sbneto/phusion-python/). To have a fully configured
container based on this image, you just have to define your credentials and the `S3CONF` variable, prepare a bucket with
your configuration files, and you are good to go (following [Phusion's way to run 
one-shot commands](https://github.com/phusion/baseimage-docker#oneshot))

```bash
docker run --rm -e S3CONF=s3://my-bucket/my.env -e S3CONF_ACCESS_KEY_ID=***access_key*** -e S3CONF_SECRET_ACCESS_KEY=***secret_access_key*** sbneto/phusion-python:3.6-env /sbin/my_init -- echo "hello world"
```
