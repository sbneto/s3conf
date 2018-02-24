# s3conf

[![Build Status](https://travis-ci.org/sbneto/s3conf.svg?branch=master)](https://travis-ci.org/sbneto/s3conf)

Utility package to help managing configuration files stored in S3-like services. Needs python 3 to work.

# Installation

```python
pip install s3conf
```

# Usage

## Configuration

This package provides a command line client `s3conf` that helps us to manipulate enviroment variables. It assumes the
environemnt variable `S3CONF` is available and points to a file in a S3-like bucket. Eg.:

```bash
export S3CONF=s3://mybucket/myfile.env
```

The client will search for authentication variables, if they are provided. The following example shows the allowed
variables.

```bash
AWS_ACCESS_KEY_ID=***access_key***
AWS_SECRET_ACCESS_KEY=***secret_access_key***
AWS_S3_REGION_NAME=***region_name***
AWS_S3_ENDPOINT_URL=***endpoint_url***
```

If these variables are not provided, the usual `boto3` credentials resolution process is used. These variables are
particularly useful for non-aws blob storage services compatible with S3, such as DigitalOcean Spaces.

If these variables are not defined, the client fallsback to a config file stored in `~/.s3conf/config.ini`, if it is
available. A convenient way to edit this file is using the client itself:

```bash
s3conf -e
```

This will open your default file editor, much like as how `crontab -e` works. 
The config file should have the following structure:

```
[default]
S3CONF=s3://mybucket/myfile.env
AWS_ACCESS_KEY_ID=***access_key***
AWS_SECRET_ACCESS_KEY=***secret_access_key***
AWS_S3_REGION_NAME=***region_name***
AWS_S3_ENDPOINT_URL=***endpoint_url***
```

Eniroment variables have precedence over variables defined in the config file.

If you create a section other than the `default` section in the ini file, you can use it passing it
as an argument.

```
[my_section]
S3CONF=s3://mybucket/myfile.env
AWS_ACCESS_KEY_ID=***access_key***
AWS_SECRET_ACCESS_KEY=***secret_access_key***
AWS_S3_REGION_NAME=***region_name***
AWS_S3_ENDPOINT_URL=***endpoint_url***
```

```bash
s3conf my_section env
```

## Environment File

Once credentials are in place, geting the data from the file defined in `S3CONF` is fairly simple. 

```bash
$ s3conf env
ENV_VAR_1=some_data_1
ENV_VAR_2=some_data_2
ENV_VAR_3=some_data_3
```

It should parse the environment file and output its values to be used with export, for instance.

```bash
$ export $(s3conf env)
```

Since editing the environment file is also common, the client provides a convenient way to do so:

```bash
s3conf env -e
```

This will download the environment file in a temporary file, open your default file editor (much like as 
`crontab -e` works) and upload the file back to the blob storage service if any edits were made (you can
edit an arbitrary file if you also pass the `-f path_to_file` to the client).

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
s3conf env -m
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
docker run --rm -e S3CONF=s3://my-bucket/my.env -e AWS_ACCESS_KEY_ID=***access_key*** -e AWS_SECRET_ACCESS_KEY=***secret_access_key*** sbneto/phusion-python:3.6-env /sbin/my_init -- echo "hello world"
```
