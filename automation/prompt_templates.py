"""Direções editoriais para criativos; não atribua características não comprovadas."""
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
COMMON = (
    "Edite a foto de referência de um produto real para um Pin vertical 2:3. "
    "Preserve rigorosamente a identidade, quantidade, formato, cor, marca, inscrições "
    "e acessórios visíveis do produto original. Não altere especificações, não crie "
    "selos, avaliações, preços, descontos, garantias nem antes/depois falsos. "
    "Não inclua texto, CTA, marca d'água nem logotipo na imagem. "
    "Composição limpa, espaço negativo e iluminação profissional. "
    "A cena é ilustrativa e será revisada por uma pessoa antes da divulgação."
)

CATEGORY_PROMPTS = {
    "casa": "Cenário residencial elegante e aconchegante, luz natural ou ambiente noturno adequado ao item, cores neutras e perspectiva editorial.",
    "tecnologia": "Ambiente de tecnologia moderno, alto contraste, enquadramento clean e superfícies discretas sem peças adicionais fictícias.",
    "organizacao": "Ambiente funcional e organizado, cenário minimalista, mostre a utilidade do item sem simular desempenho.",
    "lifestyle": "Estética lifestyle editorial, fundo acolhedor e natural, foco no produto real.",
}

def make_prompt(pin: dict) -> str:
    title = str(pin.get("title") or "produto")[:110]
    category = str(pin.get("category") or "lifestyle")
    approved_category = category if category in CATEGORY_PROMPTS else "lifestyle"
    skill = SKILLS_DIR / (approved_category + ".md")
    direction = skill.read_text(encoding="utf-8").strip() if skill.is_file() else CATEGORY_PROMPTS[approved_category]
    return f"{COMMON}\nProduto do anúncio: {title}.\nDireção: {direction[:3000]}\nNenhuma alteração factual no produto. Qualquer ambientação é ilustrativa."
