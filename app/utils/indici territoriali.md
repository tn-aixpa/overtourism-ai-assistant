# Documentazione indici territoriali


L'idea del framework è poter inserire dati sorgente arbitrari in un'unica forma canonica standardizzata.
I dati possono in seguito essere interpretati per rispondere a diverse esigenze di visualizzazione: un valore su una mappa, una serie temporale in un grafico.
Due classi svolgono tutto il lavoro:
**Fenomeno**: incapsula una singola fonte dati (es. 'posti letto per comune per anno', 'presenze da rete mobile per comune per giorno'). Un **Indice** territoriale può a sua volta essere usato come *fenomeno* di un altro Indice, per costruire macro-indicatori a partire da più sotto-indicatori.
**Indice** (territoriale): possiede una lista di **Fenomeni** più una funzione combinatore che trasforma i loro valori allineati in un unico INDICE (es. posti letto ÷ popolazione). Gestisce inoltre tutta la logica a tempo di interrogazione (es: filtraggio per data, aggregazione, ecc.)


Tutto ciò che è territoriale (quali comuni sono visibili, raggruppamento per comune o per macro-area) è gestito da esternamente: un Indice non conosce mai permessi o granularità spaziale.


---

## Glossario


| Termine | Significato |
|---|---|
| **Fenomeno** | classe che incapsula una singola fonte di dati grezzi|
| **Indice** | classe che combina più fenomeni (o altri indicatori) tramite una funzione *combinatore*, restituendo l'`INDICE` finale |
| **combinatore** | la funzione che trasforma le colonne dei fenomeni nell'`INDICE` |
| **macro area** | un gruppo di comuni con un nome (provincia / APT / ambito turistico) |


---

Numero di indicatori attualmente disponibili: **6**

- [Indice di ricettività](#indice-di-ricettività)
- [Indice di turisticità](#indice-di-turisticità)
- [Indice di incidenza ospitalità non convenzionale (strutture)](#indice-di-incidenza-ospitalità-non-convenzionale-strutture)
- [Indice di incidenza ospitalità non convenzionale (posti letto)](#indice-di-incidenza-ospitalità-non-convenzionale-posti-letto)
- [Indice di turismo sommerso](#indice-di-turismo-sommerso)
- [Indice di stagionalità delle presenze](#indice-di-stagionalità-delle-presenze)

---

## Indice di ricettività

*Classe Python: `AccommodationCapacityIndicator`*

L'indice di ricettività definisce il <strong>rapporto</strong> fra i <strong>letti presenti negli esercizi ricettivi<strong> e gli <strong>abitanti<strong> di una stessa area. L'indice è una misura della capacità turistica rispetto alla dimensione, in termini di popolazione, di un'area. L'indice è calcolato partendo dai dati ISPAT relativi alla popolazione residente e alla consistenza degli esercizi alberghieri e extra-alberghieri.

**Formula:** rapporto tra *posti letto totali* e *popolazione residente*  
`beds / population`

**Dati utilizzati:**

- **posti letto totali** (`beds`) — colonna sorgente `tot_postiletto`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale
- **popolazione residente** (`population`) — colonna sorgente `popolazione`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale

---

## Indice di turisticità

*Classe Python: `TourismIndexIndicator`*

L'indice di turisticità definisce il <strong>rapporto</strong> fra il <strong>numero medio giornaliero di turisti negli esercizi ricettivi<strong> e gli <strong>abitanti<strong> di una stessa area. L'indice è una misura dell'effettivo peso del turismo rispetto alla dimensione, in termini di popolazione, di un'area. L'indice è calcolato partendo dai dati Vodafone per quanto riguarda le presenze turistiche e dai dati ISPAT relativi alla popolazione residente.

**Formula:** rapporto tra *presenze turistiche* e *popolazione residente*  
`presences / population`

**Dati utilizzati:**

- **presenze turistiche** (`presences`) — colonna sorgente `presenze`; aggregazione: media; risoluzione temporale giornaliera (valore rilevato direttamente, senza trasformazioni); risoluzione spaziale comunale
- **popolazione residente** (`population`) — colonna sorgente `popolazione`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale

---

## Indice di incidenza ospitalità non convenzionale (strutture)

*Classe Python: `HospitalityIndexFacilitiesIndicator`*

Questo indice di incidenza dell'ospitalità non convenzionale misura il <strong>rapporto</strong> fra le <strong>strutture ricettive non convenzionali<strong> e il <strong>totale delle strutture<strong> presenti in un'area. L'indice è calcolato partendo dai dati ISPAT relativi alla consistenza degli esercizi alberghieri e extra-alberghieri.

**Formula:** rapporto tra *numero di strutture non convenzionali* e *numero totale di strutture ricettive*  
`extra_Facilities / Facilities_total`

**Dati utilizzati:**

- **numero di strutture non convenzionali** (`extra_Facilities`) — colonna sorgente `tot_strutture_non_conv`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale
- **numero totale di strutture ricettive** (`Facilities_total`) — colonna sorgente `tot_strutture`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale

---

## Indice di incidenza ospitalità non convenzionale (posti letto)

*Classe Python: `HospitalityIndexBedsIndicator`*

Questo indice di incidenza dell'ospitalità non convenzionale misura il <strong>rapporto<strong> fra il <strong>numero di posti letto in strutture ricettive non convenzionali<strong> e il <strong>numero totale di posti letto<strong> in tutte le strutture di un'area. L'indice è calcolato partendo dai dati ISPAT relativi alla consistenza degli esercizi alberghieri e extra-alberghieri.

**Formula:** rapporto tra *posti letto non convenzionali* e *posti letto totali*  
`extra_beds / beds`

**Dati utilizzati:**

- **posti letto non convenzionali** (`extra_beds`) — colonna sorgente `tot_postiletto_non_conv`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale
- **posti letto totali** (`beds`) — colonna sorgente `tot_postiletto`; aggregazione: media; risoluzione temporale annuale (valore costante propagato su tutto il periodo); risoluzione spaziale comunale

---

## Indice di turismo sommerso

*Classe Python: `HiddenTourismIndicator`*

L'indice misura il <strong>rapporto<strong> fra le <strong>presenze di turisti misurate<strong> attraverso l'analisi di dati da rete di telefonia mobile e le <strong>presenze ufficiali<strong> di turisti in strutture alberghiere e extra-alberghiere. L'analisi è a livello di ambito turistico e riguarda gli anni 2022 e 2023. L'indice è stato calcolato partendo dai dati ISPAT sul movimento turistico e dai dati Vodafone relativi alle presenze misurate.

**Formula:** calcolata con una logica personalizzata (`compute_hidden_factor`).

```python
df['presenze_vodafone'] / (df['presenze_alb'] + df['presenze_xalb'])
```

**Dati utilizzati:**

- **presenze rilevate da rete mobile (Vodafone)** (`presenze_vodafone`) — colonna sorgente `presenze_vodafone`; aggregazione: media; risoluzione temporale giornaliera (valore rilevato direttamente, senza trasformazioni); risoluzione spaziale comunale
- **presenze ufficiali alberghiere** (`presenze_alb`) — colonna sorgente `presenze_alb_distributed`; aggregazione: media; risoluzione temporale giornaliera (valore rilevato direttamente, senza trasformazioni); risoluzione spaziale comunale
- **presenze ufficiali extra-alberghiere** (`presenze_xalb`) — colonna sorgente `presenze_xalb_distributed`; aggregazione: media; risoluzione temporale giornaliera (valore rilevato direttamente, senza trasformazioni); risoluzione spaziale comunale

---

## Indice di stagionalità delle presenze

*Classe Python: `SeasonalityIndicator`*

L'indice di stagionalità definisce il <strong>rapporto</strong> fra le <strong>presenze di turisti ed escursionisti durante tra due periodi<strong> (es: anno completo ed alta stagione). L'indice è calcolato partendo dai dati Vodafone relativi alle presenze di turisti ed escursionisti.

**Formula:** calcolata con una logica personalizzata (`reference_period_over_total`).

```python
(sub_agg / total_agg.replace(0, np.nan)).values
```

**Dati utilizzati:**

- **presenze turistiche** (`presences`) — colonna sorgente `presenze_vodafone`; aggregazione: media; risoluzione temporale giornaliera (valore rilevato direttamente, senza trasformazioni); risoluzione spaziale comunale

---
