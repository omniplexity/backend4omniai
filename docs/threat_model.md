# OmniAI Threat Model

## Executive Summary

OmniAI implements a local-first AI chat interface with GitHub Pages frontend and local backend. This document outlines potential threats and mitigation strategies to ensure the system remains secure for invite-only AI chat usage.

## System Overview

- **Frontend**: Static SPA on GitHub Pages (no secrets, read-only)
- **Backend**: Local FastAPI server with SQLite database
- **Authentication**: Invite-only registration, session cookies, CSRF protection
- **Data Flow**: Frontend ↔ Local Backend ↔ LLM Providers (LM Studio/Ollama/OpenAI-compat)
- **Deployment**: Backend accessible via tunnel (Cloudflare/ngrok) with origin lock

## Threat Actors

### External Attackers
- **Motivation**: Access AI services, steal data, disrupt service
- **Capabilities**: Network attacks, web exploitation, credential stuffing
- **Access Level**: Public internet access to frontend/backend endpoints

### Malicious Users
- **Motivation**: Bypass quotas, access others' conversations, privilege escalation
- **Capabilities**: Valid user accounts, API abuse
- **Access Level**: Authenticated user sessions

### Insider Threats
- **Motivation**: Data exfiltration, system compromise
- **Capabilities**: Physical access to host machine
- **Access Level**: Local system access

## Threat Analysis

### STRIDE Classification

#### Spoofing (Authentication Bypass)

**T001: Session Hijacking**
- **Description**: Attacker steals session cookies to impersonate users
- **Impact**: Complete account takeover, access to all user data
- **Likelihood**: Medium (requires XSS or MITM)
- **Mitigations**:
  - HttpOnly cookies prevent JavaScript access
  - Secure cookies enforce HTTPS
  - Session expiry limits exposure window
  - Origin lock prevents direct backend access

**T002: CSRF Attacks**
- **Description**: Attacker tricks users into making unwanted requests
- **Impact**: Unauthorized actions (delete conversations, change settings)
- **Likelihood**: Medium (requires user interaction)
- **Mitigations**:
  - HMAC-based CSRF tokens for all state-changing requests
  - SameSite cookie settings prevent cross-site requests
  - Origin validation via CORS allowlist

#### Tampering (Data Modification)

**T003: Request Parameter Tampering**
- **Description**: Attacker modifies API parameters to access unauthorized resources
- **Impact**: Access other users' conversations or admin functions
- **Likelihood**: Low (requires authentication)
- **Mitigations**:
  - User-scoped database queries
  - Pydantic input validation
  - Admin role checks for privileged operations

**T004: Database Injection**
- **Description**: SQL injection through API parameters
- **Impact**: Data exfiltration or modification
- **Likelihood**: Low (ORM prevents raw SQL)
- **Mitigations**:
  - SQLAlchemy ORM prevents injection
  - Input sanitization via Pydantic models

#### Repudiation (Action Denial)

**T005: Audit Log Tampering**
- **Description**: Attacker modifies or deletes audit logs
- **Impact**: Security incidents cannot be investigated
- **Likelihood**: Low (requires admin access)
- **Mitigations**:
  - Database-level audit triggers
  - Immutable log entries with timestamps
  - Admin-only log access

#### Information Disclosure (Data Exposure)

**T006: Sensitive Data Leakage**
- **Description**: Provider secrets or user data exposed in responses
- **Impact**: Credential compromise, privacy violation
- **Likelihood**: Low (secrets stay backend-only)
- **Mitigations**:
  - No secrets in frontend or responses
  - Error normalization prevents stack trace leaks
  - CORS prevents unauthorized cross-origin access

**T007: Conversation Privacy Breach**
- **Description**: Users access others' conversation data
- **Impact**: Privacy violation, data leakage
- **Likelihood**: Low (scoped queries)
- **Mitigations**:
  - Database foreign key constraints
  - User ID filtering on all conversation queries
  - No admin bulk export without explicit authorization

#### Denial of Service (Service Disruption)

**T008: Resource Exhaustion**
- **Description**: Attacker consumes excessive resources
- **Impact**: Service unavailability for legitimate users
- **Likelihood**: Medium (unlimited API access)
- **Mitigations**:
  - Per-IP rate limiting
  - Per-user quota enforcement
  - Request timeouts and size limits
  - Database connection pooling

**T009: Provider Abuse**
- **Description**: Excessive API calls to LLM providers
- **Impact**: Provider account suspension, cost overrun
- **Likelihood**: High (no provider-side limits)
- **Mitigations**:
  - Daily token/message quotas
  - Rate limiting on chat endpoints
  - Generation cancellation support

#### Elevation of Privilege (Access Escalation)

**T010: Admin Privilege Escalation**
- **Description**: Regular user gains admin access
- **Impact**: Complete system compromise
- **Likelihood**: Low (role-based access)
- **Mitigations**:
  - Database role constraints
  - Admin-only endpoint guards
  - Audit logging of role changes

**T011: Invite System Abuse**
- **Description**: Unauthorized account creation
- **Impact**: User base expansion beyond intent
- **Likelihood**: Low (invite-only registration)
- **Mitigations**:
  - Invite code validation
  - Single-use invite consumption
  - Invite expiry and revocation

### Additional Threats

#### Network-Based Threats

**T012: Man-in-the-Middle**
- **Description**: Attacker intercepts traffic between frontend/backend
- **Impact**: Session hijacking, data exposure
- **Likelihood**: Medium (tunnel dependency)
- **Mitigations**:
  - HTTPS enforcement on GitHub Pages
  - Tunnel TLS encryption
  - Origin lock header validation

**T013: DNS Spoofing**
- **Description**: Attacker redirects users to malicious frontend
- **Impact**: Phishing, credential theft
- **Likelihood**: Low (GitHub Pages hosting)
- **Mitigations**:
  - GitHub's DNS security
  - HTTPS certificate validation
  - CORS origin verification

#### Local System Threats

**T014: Local Data Theft**
- **Description**: Attacker with physical/local access steals database
- **Impact**: Complete data compromise
- **Likelihood**: Low (assumes trusted local environment)
- **Mitigations**:
  - SQLite encryption (optional)
  - File system permissions
  - Secure backup storage

**T015: Provider Credential Exposure**
- **Description**: Local provider secrets compromised
- **Impact**: Unauthorized API usage
- **Likelihood**: Low (local-only access)
- **Mitigations**:
  - Environment variable isolation
  - No credential logging
  - Provider-specific authentication

## Security Controls Matrix

| Control | T001 | T002 | T003 | T004 | T005 | T006 | T007 | T008 | T009 | T010 | T011 | T012 | T013 | T014 | T015 |
|---------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
| HttpOnly Cookies | ✅ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| Secure Cookies | ✅ |  |  |  |  |  |  |  |  |  |  | ✅ | ✅ |  |  |
| CSRF Tokens |  | ✅ |  |  |  |  |  |  |  |  |  |  |  |  |  |
| User Scoping |  |  | ✅ |  |  |  | ✅ |  |  |  |  |  |  |  |  |
| Input Validation |  |  | ✅ | ✅ |  |  |  |  |  |  |  |  |  |  |  |
| Audit Logging |  |  |  |  | ✅ |  |  |  |  |  |  |  |  |  |  |
| Error Sanitization |  |  |  |  |  | ✅ |  |  |  |  |  |  |  |  |  |
| Rate Limiting |  |  |  |  |  |  |  | ✅ | ✅ |  |  |  |  |  |  |
| Quota Enforcement |  |  |  |  |  |  |  |  | ✅ |  |  |  |  |  |  |
| Role-Based Access |  |  |  |  |  |  |  |  |  | ✅ |  |  |  |  |  |
| Invite Validation |  |  |  |  |  |  |  |  |  |  | ✅ |  |  |  |  |
| HTTPS/TLS | ✅ |  |  |  |  |  |  |  |  |  |  | ✅ | ✅ |  |  |
| Origin Lock | ✅ |  |  |  |  |  |  |  |  |  |  | ✅ |  |  |  |
| CORS Allowlist |  | ✅ |  |  |  | ✅ |  |  |  |  |  | ✅ | ✅ |  |  |

## Residual Risk Assessment

### High Priority Residual Risks
- **Provider API Abuse**: No direct control over external provider rate limits
  - Mitigation: Implement client-side quotas and monitoring
- **Local System Compromise**: Physical access enables complete compromise
  - Mitigation: User education, secure local environment assumptions

### Medium Priority Residual Risks
- **Tunnel Configuration Errors**: Misconfigured tunnels expose backend
  - Mitigation: Clear deployment documentation, validation scripts
- **Dependency Vulnerabilities**: Third-party packages contain exploits
  - Mitigation: Regular dependency updates, security scanning

### Low Priority Residual Risks
- **Browser Vulnerabilities**: XSS in frontend affects users
  - Mitigation: Content Security Policy, regular frontend audits
- **Database Corruption**: SQLite corruption from system crashes
  - Mitigation: Regular backups, transaction integrity

## Security Testing Recommendations

### Automated Testing
- Unit tests for authentication logic
- Integration tests for API authorization
- Fuzzing tests for input validation
- Rate limiting effectiveness tests

### Manual Testing
- Penetration testing of deployed instance
- CORS configuration validation
- Origin lock header testing
- Session management verification

### Continuous Monitoring
- Failed authentication attempt monitoring
- Unusual rate limit triggering
- Audit log anomaly detection
- Provider error rate tracking

## Compliance Considerations

### Data Protection
- **User Data**: Conversations stored locally, user-controlled retention
- **PII Handling**: Minimal collection (username, IP for security)
- **Data Deletion**: User account deletion removes all associated data

### Privacy by Design
- **Data Minimization**: Only collect necessary user information
- **Purpose Limitation**: Data used only for authentication and chat functionality
- **Security by Default**: Secure defaults with no sensitive data exposure

## Future Security Enhancements

- **Multi-Factor Authentication**: Additional login security layer
- **Advanced Audit Features**: Log aggregation and alerting
- **Network Segmentation**: Isolate provider communications
- **Automated Security Scanning**: CI/CD security gates
- **Incident Response Plan**: Documented breach response procedures

## Conclusion

OmniAI implements defense-in-depth security with multiple overlapping controls. The local-first architecture significantly reduces attack surface compared to cloud-hosted alternatives. Primary residual risks center on local system security and proper deployment configuration, which are addressed through documentation and user education.

Regular security reviews and updates to this threat model are recommended as the system evolves.