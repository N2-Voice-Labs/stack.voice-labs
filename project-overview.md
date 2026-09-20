# Code-Switch-Aware Voice Agent for Immigration Offices in Korea

## Overview

Most automated voice systems work well in only one language, usually English. They often struggle when callers mix languages in the same sentence.

This is a real problem in Korea, where many foreign residents and students may switch between languages such as English and Russian when asking for help. In these situations, speech recognition systems can miss mixed-language words, produce incorrect transcripts, or replace what the caller actually said with unrelated phrases.

Voice systems for non-Korean and non-English languages can also be slower, which makes phone conversations frustrating.

At the same time, immigration offices receive many routine calls about topics such as:

- visa documents;
- appointments;
- office hours;
- required forms;
- general immigration procedures.

Handling these calls takes significant staff time, while there are still relatively few tools designed for multilingual and code-switched voice conversations.

## Project Goal

We are students in Korea and have seen how difficult it can be for foreigners to get help by phone when they do not speak Korean well.

Our goal is to build a voice agent that can understand conversations where users switch between English and Russian.

The first version will focus on a working prototype that can listen through a microphone, understand the caller, generate a response, and speak back naturally.

At a high level:

```text
Speech Input
    ↓
Speech-to-Text
    ↓
Response Generation
    ↓
Text-to-Speech
    ↓
Speech Output
```

We also plan to explore how this system could later be integrated into an immigration office in Korea.

## Evaluation

A major part of the project is measuring how well the system works.

We will create our own code-switched test set using recordings from native speakers who agree to participate. This will allow us to evaluate realistic English-Russian mixed-language speech.

We plan to measure:

- Word Error Rate (WER);
- transcription quality on code-switched speech;
- latency of each stage;
- total response time.

This should help us understand where recognition errors and delays come from.

## Experiments

After building the baseline system, we will test several possible improvements, including:

- vocabulary prompting with immigration-related terms such as `visa` and `alien registration card`;
- multilingual decoding;
- language-aware audio segmentation;
- other techniques that may improve mixed-language recognition.

The goal is to reduce recognition errors while keeping the system responsive enough for natural conversation.

As a later goal, we also want to test real-time streaming and interruption handling so the system behaves more like a real phone call.

## Future Languages

In the future, we want to expand beyond English and Russian.

Two important candidates are:

- Kyrgyz;
- Kazakh.

These languages generally have less available speech data than English and Russian, which makes them useful for studying how multilingual voice systems behave with lower-resource languages.

They are also relevant in Korea because many foreign residents come from Central Asian countries.

## Target Users

The initial target users are immigration office managers and public-sector administrators who want to reduce the amount of staff time spent answering routine phone calls.

The same technology could later be adapted to other areas, including:

- city helplines;
- healthcare clinics;
- logistics companies;
- customer support;
- other multilingual public services.

## Our Approach

Our team includes native speakers who understand the languages and cultural context involved.

This helps us create clearer labeling rules, review difficult code-switched sentences, and build a more realistic evaluation dataset.

Rather than relying only on large amounts of computing power, we want to combine existing voice technology with careful evaluation and native-speaker knowledge to understand how well current systems actually handle code-switched speech in Korea.