# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability within NoteAI, please send an email to [INSERT EMAIL]. All security vulnerabilities will be promptly addressed.

**Please do NOT report security vulnerabilities through public GitHub issues.**

## Disclosure Policy

When the security team receives a security bug report, they will assign it to a primary handler. This person will coordinate the fix and release process, involving the following steps:

1. Confirm the problem and determine the affected versions.
2. Audit code to find any potential similar problems.
3. Prepare fixes for all releases still under maintenance.
4. Release new versions and update the security advisory.

## Security Update

Security updates will be released as soon as possible. For critical vulnerabilities, we may issue an emergency patch.

## Scope

This policy applies to the NoteAI desktop application and its Python sidecar. It does not apply to:

- Third-party dependencies (report upstream)
- The LLM API you configure (report to your provider)
- Your local workspace data (you control this)

## Best Practices

- Keep your API keys secure; never commit them to version control
- Use environment variables or OS keyring for credentials
- Enable cloud sync only if you trust the provider
- Regularly update dependencies

## Contact

For security-related inquiries, contact: [INSERT EMAIL]
