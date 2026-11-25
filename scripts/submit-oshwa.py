#!/usr/bin/env python3
"""Preview or explicitly submit an OSHWA application; signup is a separate action."""

import argparse
import http.client
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


API_BASE = 'https://certificationapi.oshwa.org'
DEFAULT_TOKEN_FILE = Path.home() / '.config/oshwa/token'
MARK_TERMS = (
    'accurateContactInformation', 'complianceWithOfficialCertificationGuidelines',
    'oshwaCertificationMark', 'violationsEnforcement', 'responsibility',
)
DECLARATIONS = {
    'noCommercialRestriction': 'explanationNcr',
    'noDocumentationRestriction': 'explanationNdr',
    'openHardwareComponents': 'explanationOhwc',
    'creatorContribution': 'explanationCcr',
    'noUseRestriction': 'explanationNur',
    'redistributedWork': 'explanationRwr',
    'noSpecificProduct': 'explanationNsp',
    'noComponentRestriction': 'explanationNor',
    'technologyNeutral': 'explanationTn',
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward credentials or replay a registration/application POST.
        return None


def api_request(path, token=None, payload=None):
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(API_BASE + path, data=data, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode('utf-8', errors='replace')
        except (OSError, http.client.HTTPException):
            detail = 'Unable to read the error response.'
        finally:
            error.close()
        warning = ' Outcome may be unknown; check OSHWA before retrying.' if data is not None else ''
        raise RuntimeError(f'HTTP {error.code}: {detail}{warning}') from error
    except (urllib.error.URLError, OSError, http.client.HTTPException, UnicodeError) as error:
        raise RuntimeError(
            f'Request failed: {error}. Outcome may be unknown; check OSHWA before retrying.'
        ) from error
    try:
        return json.loads(body)
    except ValueError as error:
        raise RuntimeError('Non-JSON response; outcome may be unknown. Check OSHWA before retrying.') from error


def validate_submission(payload):
    for key in ['responsiblePartyType', 'responsibleParty', 'country', 'privateContact',
                'projectName', 'projectVersion', 'projectWebsite', 'documentationUrl',
                'primaryType', 'hardwareLicense', 'softwareLicense', 'documentationLicense']:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f'Fill in {key} before submitting.')
    if payload['responsiblePartyType'] not in ['Individual', 'Company', 'Organization']:
        raise ValueError('responsiblePartyType must be Individual, Company, or Organization.')
    if payload['responsiblePartyType'] != 'Individual' and not str(payload.get('bindingParty', '')).strip():
        raise ValueError('Fill in bindingParty: the person authorized to bind the company/organization.')
    if type(payload.get('availableFileFormat')) is not bool:
        raise ValueError('Explicitly set availableFileFormat to a JSON boolean.')
    for key, explanation in DECLARATIONS.items():
        if type(payload.get(key)) is not bool:
            raise ValueError(f'Explicitly set {key} to a JSON boolean, not a string.')
        if not payload[key] and not str(payload.get(explanation, '')).strip():
            raise ValueError(f'{key} is false: provide {explanation}.')
    if payload.get('agreementTerms') is not True:
        raise ValueError('Review the legal agreement and explicitly set agreementTerms to true.')
    terms = payload.get('certificationMarkTerms')
    if not isinstance(terms, dict):
        raise ValueError('Review and complete certificationMarkTerms.')
    for key in MARK_TERMS:
        term = terms.get(key)
        if not isinstance(term, dict) or term.get('agreement') is not True:
            raise ValueError(f'Review certificationMarkTerms.{key} and explicitly agree.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', nargs='?', type=Path, help='Reviewed application JSON; default: offline preview')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--submit', action='store_true', help='POST the reviewed application once')
    modes.add_argument('--options', action='store_true', help='GET accepted country/licence/type values')
    modes.add_argument('--signup', action='store_true', help='Register for an API token; does not submit an application')
    parser.add_argument('--first-name', help='API signup first name')
    parser.add_argument('--last-name', help='API signup last name')
    parser.add_argument('--email', help='API signup email')
    parser.add_argument('--token-file', type=Path, help=f'Token file (default fallback: {DEFAULT_TOKEN_FILE})')
    args = parser.parse_args(argv)
    token = None
    try:
        if args.signup:
            if args.payload:
                raise ValueError('Signup does not accept an application payload.')
            identity = {'firstName': args.first_name, 'lastName': args.last_name, 'email': args.email}
            if any(not isinstance(value, str) or not value.strip() for value in identity.values()):
                raise ValueError('--signup requires --first-name, --last-name, and --email.')
            path = (args.token_file or DEFAULT_TOKEN_FILE).expanduser()
            if path.exists() or path.is_symlink():
                raise FileExistsError(f'Token file already exists: {path}; no signup request sent.')
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Reserve a usable destination before the irreversible signup POST.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = os.fstat(fd)
            registered = False
            try:
                result = api_request('/users/signup', payload=identity)
                token = result.get('token') if isinstance(result, dict) else None
                if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                    raise RuntimeError('Signup did not return a valid token; check OSHWA before retrying.')
                registered = True
                stream = os.fdopen(fd, 'w')
                fd = None  # The stream now owns and closes the descriptor.
                with stream as saved:
                    saved.write(token + '\n')
                current = path.lstat()
                if (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino):
                    raise OSError('Token destination changed while saving.')
            except (ValueError, OSError, RuntimeError) as error:
                # Remove only our reservation/partial token, never a replacement file.
                try:
                    current = path.lstat()
                    if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                        path.unlink()
                except OSError:
                    pass
                if registered:
                    raise RuntimeError(
                        'Signup succeeded, but the token could not be safely saved. '
                        'Contact OSHWA to recover access; do not repeat --signup. '
                        f'Check {path} for an unusable partial file.'
                    ) from error
                raise
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            print(f'API token saved privately to {path}. No certification application submitted.')
            return 0

        if not args.options:
            if args.payload is None:
                raise ValueError('Provide an application JSON file, --options, or --signup.')
            payload = json.loads(args.payload.read_text())
            if not isinstance(payload, dict):
                raise ValueError('Application JSON must be an object.')
            if not args.submit:
                print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
                print('Offline preview only; nothing submitted. Review all declarations before --submit.', file=sys.stderr)
                return 0
            validate_submission(payload)
        elif args.payload:
            raise ValueError('--options does not accept an application payload.')

        if args.token_file:
            token = args.token_file.expanduser().read_text().strip()
        else:
            token = os.environ.get('OSHWA_API_TOKEN', '').strip()
            if not token and DEFAULT_TOKEN_FILE.is_file():
                token = DEFAULT_TOKEN_FILE.read_text().strip()
        if not token or any(c.isspace() for c in token):
            raise ValueError('Set OSHWA_API_TOKEN, use --token-file, or obtain a token with --signup.')
        if args.options:
            result = api_request('/api/options', token)
        else:
            result = api_request('/api/projects', token, payload)
            if not isinstance(result, dict) or result.get('success') is not True:
                raise RuntimeError('API did not confirm submission; check OSHWA before retrying.')
            print('Application submitted for review; this is not certification approval.')
        print(json.dumps(result, indent=2, ensure_ascii=False).replace(token, '[REDACTED]'))
        return 0
    except (ValueError, OSError, RuntimeError) as error:
        message = str(error).replace(token, '[REDACTED]') if token else str(error)
        print(f'OSHWA request failed: {message}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
