# API

<h2>Sobre o projeto ✍</h2>
O repositório armazena uma API em Python que recebe os dados de um script em JSON e em XLSX, depois, os repassa para uma dashboard.<br>

<h2>Tecnologias e Bibliotecas 📚</h2>
• Python - linguagem na qual o script foi feito. <br>
• Flask - Microframework web leve em Python, usado para criar a API RESTful que recebe arquivos Excel e disponibiliza os dados em formato JSON.  <br>
• Pandas - Biblioteca poderosa para manipulação e análise de dados, usada para ler, unir e processar os arquivos Excel. <br>
• Excel (.xlsx) - Formato utilizado para upload e armazenamento dos dados no backend. <br>
• NumPy: Biblioteca para computação científica, utilizada para tratar valores nulos (NaN) e facilitar a conversão para JSON válido.


<h2>Como rodar o projeto? 💻</h2>
Antes de iniciar, é necessário que sua máquina tenha uma IDE de desenvolvimento. Python e GIT instalados. Verificado isso, clone o projeto em sua máquina, usando o git bash, com o comando 

```git clone -url repositório-```. <br>

Em seguida, abra o terminal e instale as dependências: <br> 

• ```pip install flask```
• ```pip install pandas```
• ```pip install openpyxl```
• ```pip install numpy```

<br>
Rode o projeto com: <br>

• ```python app.py``` <br><br>

Se até aqui o processo foi feito corretamente, em seu terminal irá aparecer o endereço em que a API está rodando, e, ao digitar no navegador: <br>

```http://192.168.0.138:5000/dados``` <br>

Você conseguirá verificar um JSON com todos os dados recebidos do Script, que foram salvos na planilha dentro da pasta data, e que foram passados para JSON.


<hr>

Caso queira verificar como está o JSON, pode usar o arquivo que está dentro de 'tests', basta rodá-lo em seu terminal. <br>

• ```python .\tests\teste_api.py``` <br><br>

<hr>

Enfim, você terá em mãos uma API em Python que recebe os dados de um script, que aqui no meu perfil está no repositório "script-inventario". A partir do momento que a API recebe os dados técnicos da máquina, ela passa eles para um JSON e adiciona a uma planilha geral, que será enviada ao dashboard posteriormente, que, em meu perfil, está no repositório "dashboard-python".
