import { api, ApiError, loadConfig, saveConfig } from './api'

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'x',
    json: async () => body,
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  it('sends the api key and base url from settings', async () => {
    saveConfig({ baseUrl: 'https://api.example.com/', apiKey: 'k1' })
    const f = mockFetch(200, [])
    await api.accounts()
    const [url, init] = f.mock.calls[0]
    expect(url).toBe('https://api.example.com/api/accounts')
    expect(init.headers['x-api-key']).toBe('k1')
    expect(loadConfig().baseUrl).toBe('https://api.example.com')
  })

  it('falls back to the hosted runtime config, and local settings override it', () => {
    window.__CW__ = { apiUrl: 'https://hosted.example.com/' }
    expect(loadConfig().baseUrl).toBe('https://hosted.example.com/'.replace(/\/$/, ''))
    saveConfig({ baseUrl: 'http://localhost:9000', apiKey: '' })
    expect(loadConfig().baseUrl).toBe('http://localhost:9000')
    delete window.__CW__
  })

  it('omits the key header when none is set', async () => {
    const f = mockFetch(200, {})
    await api.info()
    expect(f.mock.calls[0][1].headers['x-api-key']).toBeUndefined()
  })

  it('encodes the account filter', async () => {
    const f = mockFetch(200, {})
    await api.dashboard('1 2')
    expect(f.mock.calls[0][0]).toBe('/api/dashboard?account_id=1%202')
  })

  it('posts resume values', async () => {
    const f = mockFetch(200, {})
    await api.resume('r1', { approved: true })
    expect(f.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ value: { approved: true } })
  })

  it('turns 401 into a helpful message', async () => {
    mockFetch(401, { detail: 'Missing or invalid API key' })
    await expect(api.accounts()).rejects.toThrow(/API key is missing or wrong/)
  })

  it('surfaces the server detail', async () => {
    mockFetch(404, { detail: 'Unknown run' })
    await expect(api.runStatus('x')).rejects.toMatchObject({ status: 404, message: 'Unknown run' })
  })

  it('explains an unreachable API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed')))
    const err = await api.info().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.message).toMatch(/Cannot reach/)
  })
})
