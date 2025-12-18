<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

# CastMail2List

## Usage

For production use (using gunicorn as WSGI):

```sh
castmail2list --help
```

For local development and administrative commands (using Flask directly):

```sh
castmail2list-cli --help
```

## Configuration

CastMail2List supports loading configuration from YAML files. There are some defaults and some required configuration keys.

### Using YAML Configuration

1. Copy the example configuration file:

   ```bash
   cp config.example.yaml config.yaml
   ```

2. Edit `config.yaml` with your settings

3. Run the application with the `--config` flag:
   ```bash
   castmail2list --config config.yaml
   ```

### Example Configuration File

See `config.example.yaml` for a complete example with all available configuration options.

## Copyright and Licensing

This project is mainly licensed under the Apache License 2.0, copyrighted by Max Mehl.

It also contains files from different copyright holders and under different license. As the project follows the [REUSE](https://reuse.software) best practices, you can find the according information for each individual file.
