#!/usr/bin/env python3
"""
AI-Powered Diagnostics for EdgePulse
Uses LLM to analyze system data and troubleshoot issues on edge devices.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

# Diagnostic command groups
DIAGNOSTIC_COMMANDS = {
    'system': {
        'description': 'System health (CPU, memory, uptime, services)',
        'commands': ['system_info', 'uptime', 'cpu_info', 'memory_info', 'process_list',
                     'load_average', 'top_cpu', 'dmesg_errors', 'systemd_failed']
    },
    'disk': {
        'description': 'Disk usage and I/O',
        'commands': ['disk_usage', 'disk_inodes']
    },
    'network': {
        'description': 'Network connectivity and configuration',
        'commands': ['network_interfaces', 'routing_table', 'dns_config', 'network_stats',
                     'connection_count', 'arp_table', 'listening_ports']
    },
    'docker': {
        'description': 'Docker containers status',
        'commands': ['docker_ps', 'docker_stats']
    },
    'benchmark': {
        'description': 'Benchmark client status',
        'commands': ['benchmark_status', 'benchmark_logs']
    }
}

# System prompt for diagnostic analysis
DIAGNOSTIC_SYSTEM_PROMPT = """You are an expert Linux system administrator and network engineer analyzing diagnostic data from an edge device (such as a Jetson Nano, Raspberry Pi, or similar embedded device).

Your task is to:
1. Analyze the provided diagnostic data
2. Identify any issues or anomalies
3. Determine root causes
4. Provide actionable recommendations

Format your response EXACTLY as follows:

## Health Summary
[One line overall assessment: HEALTHY, WARNING, or CRITICAL]

## Issues Found
[List each issue with severity indicator:]
- 🔴 **Critical**: [Description] (if any critical issues)
- 🟡 **Warning**: [Description] (if any warnings)
- 🟢 **OK**: [Description] (if systems are healthy)

## Root Cause Analysis
[For each issue, explain the likely cause]

## Recommendations
[Numbered list of specific, actionable steps to resolve issues]
1. [First recommendation with specific command if applicable]
2. [Second recommendation]
...

## Quick Commands
```bash
# Commands to fix the most pressing issues
[Include ready-to-run commands]
```

Be concise but thorough. Focus on the most important issues first. If data is missing for a category, note it but don't speculate."""


@dataclass
class DiagnosticSession:
    """Represents an AI diagnostic session"""
    session_id: str
    client_id: str
    created_at: str
    categories: List[str]
    status: str = 'pending'  # pending, collecting, analyzing, completed, error
    diagnostic_data: Dict[str, Any] = field(default_factory=dict)
    diagnosis: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class AITroubleshooter:
    """AI-powered system diagnostics for edge devices."""

    def __init__(self, provider: str = 'openai', api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the AI troubleshooter.

        Args:
            provider: LLM provider ('openai' or 'anthropic')
            api_key: API key (or use environment variable)
            model: Model name (defaults based on provider)
        """
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.sessions: Dict[str, DiagnosticSession] = {}

        # Set defaults based on provider
        if self.provider == 'openai':
            self.api_key = self.api_key or os.environ.get('OPENAI_API_KEY')
            self.model = self.model or 'gpt-4o'
        elif self.provider == 'anthropic':
            self.api_key = self.api_key or os.environ.get('ANTHROPIC_API_KEY')
            self.model = self.model or 'claude-3-5-sonnet-20241022'
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def is_configured(self) -> bool:
        """Check if the troubleshooter is properly configured"""
        return bool(self.api_key)

    def get_config_status(self) -> dict:
        """Get configuration status"""
        return {
            'configured': self.is_configured(),
            'provider': self.provider,
            'model': self.model,
            'has_api_key': bool(self.api_key)
        }

    def get_diagnostic_categories(self) -> dict:
        """Get available diagnostic categories"""
        return {
            category: {
                'description': info['description'],
                'commands': info['commands']
            }
            for category, info in DIAGNOSTIC_COMMANDS.items()
        }

    def create_session(self, client_id: str, categories: Optional[List[str]] = None) -> DiagnosticSession:
        """Create a new diagnostic session"""
        session = DiagnosticSession(
            session_id=str(uuid.uuid4()),
            client_id=client_id,
            created_at=datetime.now().isoformat(),
            categories=categories or ['system', 'disk', 'network']
        )
        self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[DiagnosticSession]:
        """Get a diagnostic session by ID"""
        return self.sessions.get(session_id)

    def get_commands_for_categories(self, categories: List[str]) -> List[str]:
        """Get list of commands needed for given categories"""
        commands = []
        for category in categories:
            if category in DIAGNOSTIC_COMMANDS:
                commands.extend(DIAGNOSTIC_COMMANDS[category]['commands'])
        return list(set(commands))  # Remove duplicates

    def update_session_data(self, session_id: str, command_id: str, result: dict) -> bool:
        """Update session with command result data"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.diagnostic_data[command_id] = {
            'stdout': result.get('stdout', ''),
            'stderr': result.get('stderr', ''),
            'exit_code': result.get('exit_code'),
            'executed_at': result.get('executed_at')
        }
        return True

    def _build_diagnostic_prompt(self, session: DiagnosticSession, user_question: Optional[str] = None) -> str:
        """Build the prompt with diagnostic data for LLM analysis"""
        prompt_parts = [
            f"# Edge Device Diagnostic Data",
            f"**Client ID**: {session.client_id}",
            f"**Timestamp**: {session.created_at}",
            f"**Categories Analyzed**: {', '.join(session.categories)}",
            ""
        ]

        # Add diagnostic data organized by category
        for category in session.categories:
            if category not in DIAGNOSTIC_COMMANDS:
                continue

            prompt_parts.append(f"## {category.upper()} Diagnostics")
            prompt_parts.append("")

            for cmd in DIAGNOSTIC_COMMANDS[category]['commands']:
                if cmd in session.diagnostic_data:
                    data = session.diagnostic_data[cmd]
                    prompt_parts.append(f"### {cmd}")
                    prompt_parts.append(f"Exit Code: {data.get('exit_code', 'N/A')}")
                    prompt_parts.append("```")
                    stdout = data.get('stdout', '').strip()
                    if stdout:
                        # Limit output size
                        if len(stdout) > 4000:
                            stdout = stdout[:4000] + "\n... [truncated]"
                        prompt_parts.append(stdout)
                    else:
                        prompt_parts.append("[No output]")
                    if data.get('stderr'):
                        prompt_parts.append(f"\nSTDERR: {data['stderr'][:500]}")
                    prompt_parts.append("```")
                    prompt_parts.append("")
                else:
                    prompt_parts.append(f"### {cmd}")
                    prompt_parts.append("[Data not collected]")
                    prompt_parts.append("")

        # Add user question if provided
        if user_question:
            prompt_parts.append("---")
            prompt_parts.append(f"## User Question")
            prompt_parts.append(user_question)
            prompt_parts.append("")

        prompt_parts.append("---")
        prompt_parts.append("Please analyze the above diagnostic data and provide your assessment.")

        return "\n".join(prompt_parts)

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API for analysis"""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DIAGNOSTIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3
            )

            return response.choices[0].message.content
        except ImportError:
            raise RuntimeError("OpenAI package not installed. Run: pip install openai")
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API for analysis"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)

            response = client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=DIAGNOSTIC_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            return response.content[0].text
        except ImportError:
            raise RuntimeError("Anthropic package not installed. Run: pip install anthropic")
        except Exception as e:
            raise RuntimeError(f"Anthropic API error: {str(e)}")

    def analyze(self, session_id: str, user_question: Optional[str] = None) -> dict:
        """
        Analyze collected diagnostic data using LLM.

        Args:
            session_id: The diagnostic session ID
            user_question: Optional specific question from user

        Returns:
            Dictionary with diagnosis results
        """
        session = self.sessions.get(session_id)
        if not session:
            return {'error': 'Session not found'}

        if not session.diagnostic_data:
            return {'error': 'No diagnostic data collected yet'}

        if not self.is_configured():
            return {'error': f'AI not configured. Set {self.provider.upper()}_API_KEY environment variable.'}

        try:
            session.status = 'analyzing'

            # Build prompt
            prompt = self._build_diagnostic_prompt(session, user_question)

            # Call LLM based on provider
            if self.provider == 'openai':
                diagnosis = self._call_openai(prompt)
            elif self.provider == 'anthropic':
                diagnosis = self._call_anthropic(prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            session.diagnosis = diagnosis
            session.status = 'completed'

            return {
                'session_id': session_id,
                'client_id': session.client_id,
                'status': 'completed',
                'diagnosis': diagnosis,
                'categories_analyzed': session.categories,
                'data_collected': list(session.diagnostic_data.keys())
            }

        except Exception as e:
            session.status = 'error'
            session.error = str(e)
            return {
                'session_id': session_id,
                'status': 'error',
                'error': str(e)
            }

    def quick_analyze(self, diagnostic_data: Dict[str, Any], client_id: str = 'unknown') -> dict:
        """
        Quick analysis without session management.
        Useful for one-off diagnostics.

        Args:
            diagnostic_data: Dictionary of command results
            client_id: Optional client identifier

        Returns:
            Dictionary with diagnosis results
        """
        if not self.is_configured():
            return {'error': f'AI not configured. Set {self.provider.upper()}_API_KEY environment variable.'}

        # Create temporary session
        session = DiagnosticSession(
            session_id=str(uuid.uuid4()),
            client_id=client_id,
            created_at=datetime.now().isoformat(),
            categories=['system', 'disk', 'network'],  # Default categories
            diagnostic_data=diagnostic_data
        )

        try:
            prompt = self._build_diagnostic_prompt(session)

            if self.provider == 'openai':
                diagnosis = self._call_openai(prompt)
            elif self.provider == 'anthropic':
                diagnosis = self._call_anthropic(prompt)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")

            return {
                'status': 'completed',
                'diagnosis': diagnosis,
                'client_id': client_id
            }

        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }


# Global instance (lazy initialization)
_troubleshooter = None


def get_troubleshooter() -> AITroubleshooter:
    """Get or create the global AI troubleshooter instance"""
    global _troubleshooter
    if _troubleshooter is None:
        provider = os.environ.get('AI_PROVIDER', 'openai')
        model = os.environ.get('AI_MODEL')
        _troubleshooter = AITroubleshooter(provider=provider, model=model)
    return _troubleshooter


def configure_troubleshooter(provider: str, api_key: Optional[str] = None, model: Optional[str] = None) -> AITroubleshooter:
    """Configure the global AI troubleshooter"""
    global _troubleshooter
    _troubleshooter = AITroubleshooter(provider=provider, api_key=api_key, model=model)
    return _troubleshooter
