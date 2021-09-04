High performance FTP(S) deploy
==============================

Fastest FTP deploy possible. Specific blind upload mechanism is used together 
with heavy multiprocessing and multithreading.

Installation
------------

1. Python 3 required
2. Obtain sources ``git clone https://github.com/kolinger/ftp-deploy.git``
3. Done

Configuration
-------------

Configuration is done via .json files (this shows all options).

````
{
    "local": "/local/path",
    "connection": {
        "threads": 2,
        "secure": false,
        "passive": true,
        "passive_workaround": false,
        "host": "hostname",
        "port": 21,
        "user": "username",
        "password": "password",
        "root": "/remote/path",
        "bind": "ethX"
    },
    "retry_count": 10,
    "timeout": 10,
    "ignore": [
        ".git",
        ".idea",
        "/app/config/config.local.neon",
        "/app/temp/",
        "/app/log/",
        "/assets/manager/dist",
        "/assets/client/dist",
        "/files/",
        "tests",
        "Tests",
        "examples",
        "Examples",
        "docs"
    ],
    "purge": [
        "/app/temp/cache",
        "/app/log",
        "/assets/manager/dist",
        "/assets/client/dist"
    ],
    "purge_partial": {
        "latte": "/app/temp/cache/latte",
        "neon": "/app/temp/cache/Nette.Configurator"
    },
    "purge_threads": 10,
    "composer": "/app/composer.json",
    "before": [
        "command1",
        "command2
    ],
    "after": [
        "cleanup-command"
    ]
}
````

When composer file is specified then only production dependencies are deployed (--no-dev).
Also --prefer-dist is used to exclude unnecessary files.

Basic config will look like this:
````
{
    "local": "./",
    "connection": {
        "threads": 10,
        "secure": true,
        "host": "some.server.tld",
        "user": "username",
        "password": "password",
        "root": "/www"
    },
    "ignore": [
        "/app/config/config.local.neon",
        "/app/temp/",
        "/app/log/",
        "/app/data/",
        "/assets/dist/",
        "/upload/",
        "/files/",
        ".git",
        ".idea",
        "tests",
        "Tests",
        "examples",
        "Examples",
        "docs"
    ],
    "purge": [
        "/app/temp",
        "/app/log",
        "/assets/dist"
    ]
}
````

Usage
-----

  - Config can be loaded in multiple ways:

    ``python deploy.py /path/to/my/configuration.json``
    
    or use more user-friendly pattern
    
    ``python deploy.py dev``
    
    will look for .ftp-dev.json
    
    or create local configuration file named .ftp-deploy.json and run just  
    
    ``python deploy.py``

  - Threads can be overridden with `-t|--threads`.
  
  - Before and after command can be skipped with `-s|--skip` option.
  
  - Partial purge can be activated with `-pp|--purge-partial`.
  
  - Purge threads can be overridden with `-pt|--purge-threads` or skipped with `-ps|--purge-skip`
  
  - Bind interface or source address can by specified with `-b|--bind`.
  
  - New/whole upload can be forced with `-f|--force`

  - Dry run can be set with `--dry-run`

  - All options obtainable with `--help`

Upgrade
-------

Just ```git pull```

How it works
------------
This script works in only one way. It synchronizes local files to remote FTP/FTPS server.
It is tuned to work with most FTP servers (even with the broken ones).
High performance is obtained by doing blind sync. Where we don't scan remote FTP file system.
This is crucial for performance.

Before upload this script will scan whole local tree and will compute hash for every file.
Then it tries to download special `.ftp-deployment` index file.
This file represents list of uploaded files on remote and their hash.
Then it compares local tree and hashes to content of this index file.
When mismatch is found then file is queue for upload or deletion.
After uploading/deletion new index is created and uploaded to remote as `.ftp-deployment`.
This mean we don't have idea of what is actually on remote server.
Everything is based on contents of `.ftp-deployment` file.

This means only changed files are uploaded. This improves performance by lot on large code bases.
This also means we don't ever scan whole remote tree (except for purge directories). This saves huge amount of time.

For this to work everyone in team needs to use `ftp-deploy`.
If everyone is using `ftp-deploy` then deploy will work without issues. Of course GIT is required for sync between members.
If somebody modifies FTP contents and doesn't update `.ftp-deployment` then deploy will not work as expected!
In such case full deploy needs to be done with `--force`.

This is limiting mechanism, but it brings huge performance gains. No other mechanism can compare in effectivity.

Local scanning and calculation of hashes is done in multiprocessing manner
in order to fully initialize today's many core processors with NVMe storage.

Upload, deletion, purging is all done in multithreaded manner where many parallel connections are used.
Many threads and connections will max out possible bandwidth of link.
Be careful with thread count. FTP servers will often limit maximum connection limit to 10 or 5.
If you see lots of errors bring thread count down.
Also, many threads can bring internet connection to halt. Be aware of what your ISP will be able to handle.

I prefer maximum number of thread, mostly 10 and 5 or bellow 5 for pesky FTP servers.
My previous ISP wasn't able to handle more than 2. In such case I did use VPN and did have much better
performance with many threads over VPN than with 2 threads over native link. Threads mean performance.
