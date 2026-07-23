"""
Validation schemas for PromptSmith-cli profiles and templates.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ProfileSchema:
    REQUIRED_FIELDS = ['role']
    OPTIONAL_FIELDS = {
        'name': str,
        'domain': list,
        'tone': str,
        'format': str,
        'constraints': list,
        'vendor': str,
        'version': int,
        'backend': str,
    }
    # Fields that must be lists of strings specifically, not just lists of
    # anything. Schema validation previously only checked the outer
    # container's type; a profile like domain: ["Testing", 123, null]
    # passed cleanly and then crashed with AttributeError the moment
    # _apply_rules() called .lower() on the non-string item - by then far
    # from this validation step and hard to trace back to a malformed
    # profile file.
    STRING_LIST_FIELDS = ['domain', 'constraints']

    @classmethod
    def validate(cls, data: Dict[str, Any], source: str = "unknown") -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError(f"Profile in {source} must be a dictionary, got {type(data).__name__}")
        missing = [f for f in cls.REQUIRED_FIELDS if f not in data]
        if missing:
            raise ValueError(f"Profile in {source} is missing required fields: {', '.join(missing)}")
        errors = []
        if 'role' in data and not isinstance(data['role'], str):
            errors.append(f"'role' must be a string, got {type(data['role']).__name__}")
        for field, expected_type in cls.OPTIONAL_FIELDS.items():
            if field in data and not isinstance(data[field], expected_type):
                if expected_type is list and not isinstance(data[field], (list, tuple)):
                    errors.append(f"'{field}' must be a list, got {type(data[field]).__name__}")
                elif not isinstance(data[field], expected_type):
                    errors.append(f"'{field}' must be {expected_type.__name__}, got {type(data[field]).__name__}")
        for field in cls.STRING_LIST_FIELDS:
            if field in data and isinstance(data[field], (list, tuple)):
                bad_items = [item for item in data[field] if not isinstance(item, str)]
                if bad_items:
                    errors.append(
                        f"'{field}' must contain only strings, found "
                        f"{[type(item).__name__ for item in bad_items]}"
                    )
        if 'version' in data:
            if not isinstance(data['version'], int) or data['version'] < 1:
                errors.append("'version' must be a positive integer")
        if errors:
            raise ValueError(f"Profile in {source} has validation errors: {', '.join(errors)}")
        result = dict(data)
        if 'domain' not in result:
            result['domain'] = []
        if 'tone' not in result:
            result['tone'] = 'neutral'
        if 'format' not in result:
            result['format'] = 'text'
        if 'constraints' not in result:
            result['constraints'] = []
        if 'version' not in result:
            result['version'] = 1
        if 'backend' not in result:
            result['backend'] = 'rule'
        return result


class TemplateSchema:
    REQUIRED_FIELDS = ['prompt']
    OPTIONAL_FIELDS = {
        'name': str,
        'description': str,
        'version': int,
    }
    
    @classmethod
    def validate(cls, data: Dict[str, Any], source: str = "unknown") -> Dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError(f"Template in {source} must be a dictionary, got {type(data).__name__}")
        missing = [f for f in cls.REQUIRED_FIELDS if f not in data]
        if missing:
            raise ValueError(f"Template in {source} is missing required fields: {', '.join(missing)}")
        if not isinstance(data.get('prompt'), str):
            raise ValueError(f"Template 'prompt' in {source} must be a string")
        if 'version' in data:
            if not isinstance(data['version'], int) or data['version'] < 1:
                raise ValueError(f"Template 'version' in {source} must be a positive integer")
        result = dict(data)
        if 'version' not in result:
            result['version'] = 1
        return result


def validate_profile(data: Dict[str, Any], source: str = "unknown") -> Dict[str, Any]:
    try:
        return ProfileSchema.validate(data, source)
    except ValueError as e:
        logger.error(f"Profile validation failed for {source}: {e}")
        raise


def validate_template(data: Dict[str, Any], source: str = "unknown") -> Dict[str, Any]:
    try:
        return TemplateSchema.validate(data, source)
    except ValueError as e:
        logger.error(f"Template validation failed for {source}: {e}")
        raise