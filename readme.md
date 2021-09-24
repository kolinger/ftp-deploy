High performance FTP(S) deploy
==============================

Fastest FTP deploy possible. Specific blind upload mechanism is used together 
with multiprocessing and multithreading to minimize deploy time and also downtime.

#### What it can do?
- Deploy local files to remote FTP(S) server efficiently. Only changed files are uploaded. Files are compared 
by contents - hash (not by date or size).
- Exclude unnecessary or unwanted files.
- Purge specific directories (cache, logs, ...).
- Run local commands before/after deploy.
- Prepare Composer dependencies where dev dependencies are excluded.

Main use of this tool is for public web hosting services where only FTP(S) is available and no other protocol 
can be used. But it's also useful for private servers since FTPS is more efficient than other transfer protocols.

#### What it can't do?
- It can't do anything other than synchronize local files to remote FTP(S) server.
- It can't do two-way sync, reverse sync, ...
- It can't use any other protocols (SFTP, SCP, ...).

#### Limitations
- All developers sharing access need to use this tool in order to make differential sync work properly. This tool 
uses index file where all files are tracked. When file changes outside this index then differential sync will 
not see these changes and thus will fail to work properly. This situation can't be detected and tool will 
report successful transfer, yet it may fail to replace some files and this may result in silently broken deploy.
- Active FTP won't work most of the time by design - passive FTP is required.

#### Purge notes
- Purge removes all files and directories recursively
- **Purge removes everything including ignored/excluded patterns!**
- If target is file - file is simple deleted
- If target is directory - directory is first renamed to temporary name and new directory is created as replacement.
This is done to remove directory (like cache) immediately. Since directory can have many files and all files need
to be removed one by one. This can take long time. Rename is one command, recursive deletion of directory can be 
thousands of commands. Thus purge has immediate effect and rest of purge can be long but application won't be affected 
by this delay since all files or directories don't exist from view of application.

#### Why make custom tool for comparing file tree changes when tools like GIT exist?
This tool doesn't use GIT since deploy based on GIT commits is not good idea. In real world GIT deploy will eventually
force developers to make nonsense commits just to trigger temporary deploy when debugging. Maybe not in theory but
real world is different from theory and best case practices. GIT and other version control tools are not designed 
for deploy. GIT deploy may work for some but not for others. Self-contained tool can work for everyone.

Installation
------------

1. [Python 3](https://www.python.org/downloads/) required

2. Obtain sources `git clone https://github.com/kolinger/ftp-deploy.git` or 
[download zip](https://github.com/kolinger/ftp-deploy/archive/refs/heads/master.zip)

3. Done

(no other dependencies are required expect for python itself)

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

When composer file is specified then only production dependencies are deployed (`--no-dev`).
Also `--prefer-dist` is used to exclude unnecessary files.

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

Just `git pull` or [download zip](https://github.com/kolinger/ftp-deploy/archive/refs/heads/master.zip)

Speed of FTP
------------
When uploading many small files over FTP then a lot of small transactions are needed. And in such scenario latency 
will limit bandwidth and thus only more parallel connections (threads) will improve speed. You will see more and more
improvement from threads the worse connection you have or the more distance you have between you and server.

This is what `"threads"` and `"purge_threads"` are for. We want to set thread count as high as possible.
But we can't just set any number since FTP servers often limit maximum number of connections per user or/and IP.
Also, high thread count will result in many connections and this may clog your router or trigger 
limitation of your ISP. If your internet stops working, or you see a lot of errors -> lower thread count.

Most time 10 or 5 threads will work but sometimes <5 is required.

If your ISP is very restrictive and will not allow even 5 threads then you may benefit using VPN. I have experience
where ISP couldn't handle more than 2 threads but 10 threads over VPN did work and did give huge improvements.

How it works
------------
Before upload this tool will scan local tree and compute hash for every file.
Then it tries to download index file from remote (`.deployment-index` ).
This index represents list of uploaded files on remote and their hash.
Then it compares local tree and hashes to content of this index file.
When mismatch is found then file is queued for upload or deletion.
After uploading/deletion new index is created and uploaded to remote as `.deployment-index`.
This means we don't have idea of what is actually on remote server.
Everything is based on contents of index (`.deployment-index` file).

This mechanism creates bunch of limitations but any other mechanism will need to scan remote tree and 
that is very expensive operation over FTP(S) and thus very slow in real world.
