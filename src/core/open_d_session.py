"""OpenD session management for the moomoo/Futu OpenAPI.

This module provides a minimal wrapper for maintaining a connection to the local OpenD gateway.
"""

class OpenDSession:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.connected: bool = False

    def connect(self) -> None:
        """Establish a connection to the OpenD gateway.

        This is a placeholder. Actual implementation will depend on the moomoo/futu SDK.
        """
        # TODO: Implement connection using futu API
        self.connected = True

    def close(self) -> None:
        """Close the connection to the OpenD gateway."""
        # TODO: Close any active sessions
        self.connected = False
