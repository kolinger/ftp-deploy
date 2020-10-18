Fast FTP deploy
===============

Installation
------------

1. Python 2.7 required
2. Obtain sources ``git clone https://bitbucket.org/kolinger/ftp-deploy.git``
3. Done

Configuration
-------------

Configuration is done via .json files.

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

Upgrade
-------

Just ```git pull```
