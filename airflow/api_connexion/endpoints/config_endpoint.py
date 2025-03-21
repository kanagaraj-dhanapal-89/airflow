# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

from http import HTTPStatus

from flask import Response, request

from airflow.api_connexion import security
from airflow.api_connexion.exceptions import NotFound, PermissionDenied
from airflow.api_connexion.schemas.config_schema import Config, ConfigOption, ConfigSection, config_schema
from airflow.configuration import conf
from airflow.settings import json
from airflow.utils.api_migration import mark_fastapi_migration_done

LINE_SEP = "\n"  # `\n` cannot appear in f-strings


def _conf_dict_to_config(conf_dict: dict) -> Config:
    """Convert config dict to a Config object."""
    config = Config(
        sections=[
            ConfigSection(
                name=section, options=[ConfigOption(key=key, value=value) for key, value in options.items()]
            )
            for section, options in conf_dict.items()
        ]
    )
    return config


def _option_to_text(config_option: ConfigOption) -> str:
    """Convert a single config option to text."""
    return f"{config_option.key} = {config_option.value}"


def _section_to_text(config_section: ConfigSection) -> str:
    """Convert a single config section to text."""
    return (
        f"[{config_section.name}]{LINE_SEP}"
        f"{LINE_SEP.join(_option_to_text(option) for option in config_section.options)}{LINE_SEP}"
    )


def _config_to_text(config: Config) -> str:
    """Convert the entire config to text."""
    return LINE_SEP.join(_section_to_text(s) for s in config.sections)


def _config_to_json(config: Config) -> str:
    """Convert a Config object to a JSON formatted string."""
    return json.dumps(config_schema.dump(config), indent=4)


@mark_fastapi_migration_done
@security.requires_access_configuration("GET")
def get_config(*, section: str | None = None) -> Response:
    """Get current configuration."""
    serializer = {
        "text/plain": _config_to_text,
        "application/json": _config_to_json,
    }
    return_type = request.accept_mimetypes.best_match(serializer.keys())
    if conf.get("webserver", "expose_config").lower() == "non-sensitive-only":
        expose_config = True
        display_sensitive = False
    else:
        expose_config = conf.getboolean("webserver", "expose_config")
        display_sensitive = True

    if return_type not in serializer:
        return Response(status=HTTPStatus.NOT_ACCEPTABLE)
    elif expose_config:
        if section and not conf.has_section(section):
            raise NotFound("section not found.", detail=f"section={section} not found.")
        conf_dict = conf.as_dict(display_source=False, display_sensitive=display_sensitive)
        if section:
            conf_section_value = conf_dict[section]
            conf_dict.clear()
            conf_dict[section] = conf_section_value
        config = _conf_dict_to_config(conf_dict)
        config_text = serializer[return_type](config)
        return Response(config_text, headers={"Content-Type": return_type})
    else:
        raise PermissionDenied(
            detail=(
                "Your Airflow administrator chose not to expose the configuration, most likely for security"
                " reasons."
            )
        )


@mark_fastapi_migration_done
@security.requires_access_configuration("GET")
def get_value(*, section: str, option: str) -> Response:
    serializer = {
        "text/plain": _config_to_text,
        "application/json": _config_to_json,
    }
    return_type = request.accept_mimetypes.best_match(serializer.keys())
    if conf.get("webserver", "expose_config").lower() == "non-sensitive-only":
        expose_config = True
    else:
        expose_config = conf.getboolean("webserver", "expose_config")

    if return_type not in serializer:
        return Response(status=HTTPStatus.NOT_ACCEPTABLE)
    elif expose_config:
        if not conf.has_option(section, option):
            raise NotFound(
                "Config not found.", detail=f"The option [{section}/{option}] is not found in config."
            )

        if (section.lower(), option.lower()) in conf.sensitive_config_values:
            value = "< hidden >"
        else:
            value = conf.get(section, option)

        config = Config(
            sections=[ConfigSection(name=section, options=[ConfigOption(key=option, value=value)])]
        )
        config_text = serializer[return_type](config)
        return Response(config_text, headers={"Content-Type": return_type})
    else:
        raise PermissionDenied(
            detail=(
                "Your Airflow administrator chose not to expose the configuration, most likely for security"
                " reasons."
            )
        )
