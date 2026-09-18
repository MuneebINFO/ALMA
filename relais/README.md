# Le relais d'abonnement

Le petit serveur qui se tient entre ALMA et l'API d'Anthropic. Il existe pour
une seule raison : **la clé d'API ne peut pas voyager dans l'application**.

Un `.msix` est une archive. On en sort l'exécutable, on y cherche des chaînes,
et la clé est là — même obfusquée, elle doit être en clair en mémoire au
moment de l'appel. Une clé livrée est une clé publiée, et c'est le compte de
l'éditeur qui paie, sans plafond.

```
ALMA  ──(jeton signé par Microsoft)──▶  CE RELAIS  ──(votre clé)──▶  Anthropic
```

## Ce qu'il fait, et ce qu'il ne fait pas

Il vérifie que l'abonnement est actif, décompte le quota mensuel, transmet la
requête, renvoie la réponse.

Il **ne conserve ni les questions, ni les images, ni les réponses**. Ce qu'il
garde est un compteur par abonné — le strict nécessaire pour un quota.
`PRIVACY.md` en fait la promesse aux utilisateurs, et `test_relais.py` la
garde : un test ouvre la base après une requête et vérifie qu'aucun fragment
du contenu ne s'y trouve.

## Démarrer en local, tout de suite

Aucun compte Azure n'est nécessaire pour éprouver le relais.

```bash
pip install -r relais/requirements.txt
ANTHROPIC_API_KEY=sk-ant-... uvicorn relais:app --app-dir relais --reload
```

Il démarre alors en **mode développement** : il n'accepte que le jeton d'essai
(`essai-local` par défaut) et refuse tout le reste. Le mode est journalisé à
chaque démarrage — c'est volontaire, pour qu'un relais parti en production
dans cet état se remarque tout de suite.

```bash
curl -s localhost:8000/sante
curl -s localhost:8000/v1/messages -H "x-api-key: essai-local" \
     -H "content-type: application/json" \
     -d '{"model":"claude-sonnet-5","max_tokens":100,
          "messages":[{"role":"user","content":"bonjour"}]}'
```

Les tests :

```bash
pytest relais/test_relais.py
```

## Passer en production

### 1. Les variables d'environnement

| Variable | Rôle |
|---|---|
| `ANTHROPIC_API_KEY` | **Votre** clé. Jamais dans le dépôt, jamais dans l'image — posée chez l'hébergeur |
| `AZURE_CLIENT_ID` | L'application Azure AD liée à votre compte Partner Center |
| `AZURE_CLIENT_SECRET` | Son secret |
| `AZURE_TENANT_ID` | Votre locataire Azure |
| `ALMA_QUOTA_MENSUEL` | Requêtes incluses par mois (300 par défaut) |
| `ALMA_BASE` | Chemin de la base SQLite — **sur un volume persistant** |

Tant que `AZURE_CLIENT_ID` et `AZURE_CLIENT_SECRET` sont absents, le relais
reste en mode développement et **aucun vrai abonné ne peut passer**. C'est la
dernière chose à provisionner, et elle n'est pas optionnelle.

### 2. Azure AD

Le relais doit pouvoir demander à Microsoft « cette personne est-elle
abonnée ? ». Cela suppose une application Azure AD associée au compte Partner
Center, avec l'accès au service de collections du Store.

⚠️ **Les adresses du service de collections sont à confirmer** contre la
documentation Microsoft à jour avant la mise en production. Elles sont
isolées dans `_demander_a_microsoft()` et `_jeton_azure()` — deux fonctions,
rien d'autre à corriger si Microsoft les fait évoluer. Le principe, lui, ne
change pas.

### 3. La persistance

La base SQLite porte les compteurs de quota. Sur un hébergement éphémère
(conteneur redémarré, système de fichiers volatile), **elle disparaît à chaque
redéploiement** — et tous les quotas repartent de zéro, ce qui coûte de
l'argent en silence.

Montez un volume persistant et pointez `ALMA_BASE` dessus.

### 4. L'application

Rien à recompiler côté ALMA : le SDK accepte une `base_url`. Le provider
envoie alors le jeton d'abonné là où il mettait une clé.

## Pourquoi cette forme d'API

Le point d'entrée `/v1/messages` a **exactement la même forme** que celui
d'Anthropic. C'est ce qui rend le basculement minuscule côté application — et
ce qui permet de revenir en arrière en changeant une seule valeur, si le
relais tombe.

## Les décisions à connaître

**Le cache d'abonnement.** Interroger Microsoft à chaque requête ajouterait un
aller-retour à chaque phrase prononcée. La réponse est donc gardée douze
heures : assez pour que la latence ne se paie qu'une fois, assez peu pour
qu'une résiliation soit prise en compte dans la journée.

**Une panne ne consomme pas de quota.** Si l'amont est injoignable, le
compteur n'avance pas. Faire payer un quota pour un incident de notre côté
serait doublement injuste.

**Les en-têtes sont filtrés.** Seules `content-type`, `anthropic-version` et
`anthropic-beta` sont transmises. Un relais qui retransmet aveuglément devient
le proxy ouvert de quelqu'un d'autre.
