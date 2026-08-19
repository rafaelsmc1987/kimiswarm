import requests
def CapturarSkills(accessToken):
    cookies = {
        'theme': 'dark',
        'g_state': '{"i_l":0,"i_ll":1785557323085,"i_b":"PChrjaaY67SZ56OR6nCppsXCwpdHm2GsSfSjGNWvqRQ","i_e":{"enable_itp_optimization":24},"i_et":1785557323085}',
        '_ga': 'GA1.1.1334088619.1785557323',
        'next-sidebar-publisher-shortcut-region': '22',
        '__snaker__id': 'egQbrABdiKzU6R93',
        'intercom-device-id-qhdj3uun': '55621af4-25b3-4ff6-ab70-5cad4405f454',
        'gdxidpyhxdE': 'woYe8RzWqZ3rNPSAIVkyx3ZDB%5CWOtOt2Z5%2Far4K00YarRMj4yQ9fqimMLpW5ghWn3J%5CucHce8WYHxSPO4gh4mYg2Opl9gUK8RhtNHMDNY0mmp3JkYP5j7zd%2FWHYMQxSKowW%2FvcCVs34rwlZaoCj5AIP%2FkUOqzCiMTV5YINTTMHiaA4xq%3A1785815532711',
        'next-sidebar-more-expanded': 'true',
        'Hm_lvt_358cae4815e85d48f7e8ab7f3680a74b': '1785940685,1786120596,1786465766,1786572673',
        'HMACCOUNT': 'B6FACD8263E1FCEA',
        '_gcl_au': '1.1.953381745.1785557323.403009236.1786600629.1786600673.7660872.1786600629.1786600673',
        '__cf_bm': '.dC2Lq7yiegbt0CcqzJ62jPC1nw5kgoj8NRc3saZbqQ-1786933110.3678694-1.0.1.1-St9Sr8haBQpGr1Fjj.BRWNadjYQH_WNHJWRUYeBAPnrxVCOBD5prIfMnZ5DGiIokblNkdRy..1aaQS4vkWKX2Pgb8AdG_54lyDlZelmeIn5xAz0BCZOJpCHQ6pSFSGPh',
        'intercom-session-qhdj3uun': 'R28zZ0h6ejBYclh6L3MvdzNCd0p2VlN4K0d0UVQyOVF4WWxCM3BpQ01sWmgyTGF6MXducGhkMk53T1VXQmwrakE0ZVRXejdjUm5KaGtDc0lmUXJGZTNiMDUxdUl5SElpUURISVcwR3J4KzMwWXgwRzBjeWdma1gyMktpUXVMNUhkOTEzOThTemFudHkzYmh4RnNoUkZUcG1hZmVJdk0xWEY4cEQ1TDhKZGc1bDRlYThXSlY5Z29YOFNsbjc2WVJRVlVUQVZuNzQyejlINjd5VWU0UU5TRlJPN1cwV3k3dUFJRkc2SlpDMVFFdz0tLS9Tc2FlRHBpZlpxek41VlhFZkdsR1E9PQ==--5fea4deab6533d69c2a5f94911128fbb9c47dad1',
        '_ga_YXD8W70SZP': 'GS2.1.s1786933111$o30$g1$t1786933821$j59$l0$h0',
        'Hm_lpvt_358cae4815e85d48f7e8ab7f3680a74b': '1786933822',
    }

    headers = {
        'accept': '*/*',
        'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5',
        'authorization': f'Bearer {accessToken}',
        'connect-protocol-version': '1',
        'content-type': 'application/json',
        'origin': 'https://www.kimi.com',
        'priority': 'u=1, i',
        'r-timezone': 'America/Sao_Paulo',
        'referer': 'https://www.kimi.com/skills',
        'sec-ch-ua': '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
        'x-language': 'pt-BR',
        'x-msh-device-id': '7668910311713299712',
        'x-msh-platform': 'web',
        'x-msh-session-id': '1731715420663060787',
        'x-msh-shield-data': 'sg:OUAHNWNr5PKSBJ64wyot0OmgxY',
        'x-msh-version': '2.0.0',
        'x-traffic-id': 'd9mn2qasc5ci404j455g',
        # 'cookie': 'theme=dark; g_state={"i_l":0,"i_ll":1785557323085,"i_b":"PChrjaaY67SZ56OR6nCppsXCwpdHm2GsSfSjGNWvqRQ","i_e":{"enable_itp_optimization":24},"i_et":1785557323085}; _ga=GA1.1.1334088619.1785557323; next-sidebar-publisher-shortcut-region=22; __snaker__id=egQbrABdiKzU6R93; intercom-device-id-qhdj3uun=55621af4-25b3-4ff6-ab70-5cad4405f454; gdxidpyhxdE=woYe8RzWqZ3rNPSAIVkyx3ZDB%5CWOtOt2Z5%2Far4K00YarRMj4yQ9fqimMLpW5ghWn3J%5CucHce8WYHxSPO4gh4mYg2Opl9gUK8RhtNHMDNY0mmp3JkYP5j7zd%2FWHYMQxSKowW%2FvcCVs34rwlZaoCj5AIP%2FkUOqzCiMTV5YINTTMHiaA4xq%3A1785815532711; next-sidebar-more-expanded=true; Hm_lvt_358cae4815e85d48f7e8ab7f3680a74b=1785940685,1786120596,1786465766,1786572673; HMACCOUNT=B6FACD8263E1FCEA; _gcl_au=1.1.953381745.1785557323.403009236.1786600629.1786600673.7660872.1786600629.1786600673; __cf_bm=.dC2Lq7yiegbt0CcqzJ62jPC1nw5kgoj8NRc3saZbqQ-1786933110.3678694-1.0.1.1-St9Sr8haBQpGr1Fjj.BRWNadjYQH_WNHJWRUYeBAPnrxVCOBD5prIfMnZ5DGiIokblNkdRy..1aaQS4vkWKX2Pgb8AdG_54lyDlZelmeIn5xAz0BCZOJpCHQ6pSFSGPh; intercom-session-qhdj3uun=R28zZ0h6ejBYclh6L3MvdzNCd0p2VlN4K0d0UVQyOVF4WWxCM3BpQ01sWmgyTGF6MXducGhkMk53T1VXQmwrakE0ZVRXejdjUm5KaGtDc0lmUXJGZTNiMDUxdUl5SElpUURISVcwR3J4KzMwWXgwRzBjeWdma1gyMktpUXVMNUhkOTEzOThTemFudHkzYmh4RnNoUkZUcG1hZmVJdk0xWEY4cEQ1TDhKZGc1bDRlYThXSlY5Z29YOFNsbjc2WVJRVlVUQVZuNzQyejlINjd5VWU0UU5TRlJPN1cwV3k3dUFJRkc2SlpDMVFFdz0tLS9Tc2FlRHBpZlpxek41VlhFZkdsR1E9PQ==--5fea4deab6533d69c2a5f94911128fbb9c47dad1; _ga_YXD8W70SZP=GS2.1.s1786933111$o30$g1$t1786933821$j59$l0$h0; Hm_lpvt_358cae4815e85d48f7e8ab7f3680a74b=1786933822',
    }

    json_data = {
        'page_size': 1000,
       
    }

    response = requests.post(
        'https://www.kimi.com/apiv2/kimi.gateway.skill.v1.SkillService/ListOfficialSkills',
        cookies=cookies,
        headers=headers,
        json=json_data,
    )
    Resposta = response.text
    print(Resposta)

def RefreshToken():
    headers = {
        'x-msh-session-id': '1731715420663060787',
        'sec-ch-ua-platform': '"Windows"',
        'Referer': 'https://www.kimi.com/',
        'x-msh-platform': 'web',
        'x-msh-device-id': '7668910311713299712',
        'sec-ch-ua': '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
        'sec-ch-ua-mobile': '?0',
        'connect-protocol-version': '1',
        'x-msh-version': '2.0.0',
        'r-timezone': 'America/Sao_Paulo',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
        'content-type': 'application/json',
        'x-msh-shield-data': 'sg:jDe4TWc43TievfgFDexFgIrQBE',
        'x-traffic-id': 'd9mn2qasc5ci404j455g',
    }

    json_data = {
        'refresh_token': 'eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJhY2NvdW50IiwiYXVkIjpbImtpbWkuYWkiXSwiZXhwIjoxNzk0NzA5MTE1LCJpYXQiOjE3ODY5MzMxMTUsImp0aSI6ImRhMTZ1dXY5YW5tbHRya3FhaDZnIiwidHlwIjoicmVmcmVzaCIsImFwcF9pZCI6ImtpbWkiLCJzdWIiOiJkOW1uMnFhc2M1Y2k0MDRqNDU1ZyIsImFic3RyYWN0X3VzZXJfaWQiOiJkOW1uMnFhc2M1Y2k0MDRqNDVwZyIsInNzaWQiOiIxNzMxNzE1NDIwNjYzMDYwNzg3IiwiZGV2aWNlX2lkIjoiNzY2ODkxMDMxMTcxMzI5OTcxMiIsInJlZ2lvbiI6Im92ZXJzZWFzIiwibWVtYmVyc2hpcCI6eyJsZXZlbCI6Mjd9LCJjb2RlX21lbWJlcnNoaXAiOnsibGV2ZWwiOjI3fX0.H0fbs8r4hMTWIbZ2vudxJVCj3fjT6Q6g3F3JqkNtrHdy0kXWinTj8KyvhpeIwJXVlA9XEATEgQDnXTMOBeA73A',
    }

    response = requests.post(
        'https://auth.kimi.com/api/account.gateway.v1.AuthService/RefreshToken',
        headers=headers,
        json=json_data,
    )
    Resposta = response.json()
    accessToken = Resposta['accessToken']
    print(accessToken)
    return accessToken

accessToken = RefreshToken()
CapturarSkills(accessToken)