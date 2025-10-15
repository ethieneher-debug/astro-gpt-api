from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_URL = "https://astro-gpt-api-fgpp.onrender.com/chart_text_br"

def chamar_api_astro(nome, sexo, data, hora, cidade_estado, pais):
    payload = {
        "nome": nome,
        "sexo": sexo,
        "data": data,
        "hora": hora,
        "cidade_estado": cidade_estado,
        "pais": pais
    }
    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(API_URL, json=payload, headers=headers)

    if response.status_code == 200:
        return response.text
    else:
        return f"Erro ao consultar mapa: {response.status_code} - {response.text}"

@app.route('/mapa_natal', methods=['POST'])
def gerar_mapa():
    data_input = request.get_json()

    try:
        nome = data_input.get("nome", "Cliente")
        sexo = data_input.get("sexo", "não informado")
        data = data_input["data"]
        hora = data_input["hora"]
        cidade_estado = data_input["cidade_estado"]
        pais = data_input["pais"]

        resultado = chamar_api_astro(nome, sexo, data, hora, cidade_estado, pais)
        return jsonify({
            "resultado": resultado
        })

    except KeyError as e:
        return jsonify({"erro": f"Campo obrigatório ausente: {str(e)}"}), 400

if __name__ == '__main__':
    app.run(debug=True)
