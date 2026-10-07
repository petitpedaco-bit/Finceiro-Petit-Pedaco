"""Download limitado de planilhas públicas com redirecionamentos Google."""
import re
import httpx


async def download_google_sheet(url: str, transport=None) -> bytes:
    match = re.fullmatch(r'https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]+)(?:/[^\s]*)?', url.strip())
    if not match:
        raise ValueError('Informe um link válido de Google Sheets')
    current = httpx.URL(f'https://docs.google.com/spreadsheets/d/{match[1]}/export?format=xlsx')
    async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15), transport=transport) as client:
        for _ in range(6):
            host = current.host or ''
            if current.scheme != 'https' or not (
                host == 'docs.google.com' or host.endswith('.googleusercontent.com')
            ):
                raise ValueError('O Google solicitou login. Compartilhe para visualização por link.')
            async with client.stream('GET', current) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get('location')
                    if not location:
                        raise ValueError('Redirecionamento Google sem endereço de destino')
                    current = response.url.join(location)
                    continue
                if response.status_code in (401, 403, 404):
                    raise ValueError('Planilha indisponível. Confira o link e a permissão de visualização.')
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 20 * 1024 * 1024:
                        raise ValueError('Arquivo excede 20 MB')
                if not data.startswith(b'PK'):
                    raise ValueError('O Google não retornou Excel. Confira o compartilhamento da planilha.')
                return bytes(data)
    raise ValueError('O Google excedeu o limite de redirecionamentos')
