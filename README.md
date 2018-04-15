# s3conf

[![Build Status](https://travis-ci.org/sbneto/s3conf.svg?branch=master)](https://travis-ci.org/sbneto/s3conf)

Utility package to help managing configuration files stored in S3-like services. Needs python3.

# Installation

```python
pip install s3conf
```

# Usage

## Configuration

This package provides a command line client `s3conf` that helps us to manipulate enviroment variables.
It looks for a configuration variable named `S3CONF` that should point to a file in a S3-like bucket. Eg.:

```bash
export S3CONF=s3://mybucket/myfile.env
```

If you have a `aws-cli` working, this should already be enough to get you started.

## Credentials Resolution

In order to find the `S3CONF` variable and other credentials variables, it uses a credentials resolution 
that flows like this:

1) Environment Variables
2) Configuration File in the current folder: `./.s3conf/config`
3) Configuration File in the user folder: `~/.s3conf`
4) Boto3 configuration resolution

The client will search for these authentication variables, if they are provided:

```bash
S3CONF_ACCESS_KEY_ID=***access_key***
S3CONF_SECRET_ACCESS_KEY=***secret_access_key***
S3CONF_S3_REGION_NAME=***region_name***
S3CONF_S3_ENDPOINT_URL=***endpoint_url***
```

These variables map to their `AWS_` counterpart that are used for regular Boto3 configuration.
The cliendt also searchs for the regular `AWS_` variables, but the client variables take precedence. 
They are particularly useful when using non-aws blob storage services compatible with S3, such as DigitalOcean Spaces,
without messing your AWS credentials.

Each variable lookup will follow the resolution order and the client will use the first one it finds, 
meaning you can keep the `S3CONF` variable defined in you working directory and your credentials 
in your user folder, for example.

You can create multiple sections in your current folder Configuration File:

```ini
[dev]
S3CONF=s3://my-dev-bucket/myfile.env

[prod]
S3CONF=s3://my-prod-bucket/myfile.env
```

And inform the client to use the rigth section:

```bash
s3conf env dev
```

## Editing Your Config Files

A convenient way to edit the Configuration File in your current folder is to use the following command:

```bash
s3conf -e
```

This will open your default file editor, much like as how `crontab -e` works. To edit the Configuration File 
in your user's folder, you can use the following command:

```bash
s3conf -e --global
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
