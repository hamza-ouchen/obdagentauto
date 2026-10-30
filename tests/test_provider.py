import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app import llm


class ProviderTest(unittest.TestCase):
    def response(self,text='Explication fondée sur la fiche technique.',usage=None):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))],usage=usage)

    def test_cached_token_pricing(self):
        usage=SimpleNamespace(prompt_tokens=100,completion_tokens=20,prompt_tokens_details=SimpleNamespace(cached_tokens=40))
        with patch.dict(os.environ,{'LLM_PROVIDER':'openrouter','LLM_MODEL':'openai/gpt-4o-mini','OPENROUTER_API_KEY':'test-only'}),patch('app.llm.OpenAI') as client:
            client.return_value.chat.completions.create.return_value=self.response(usage=usage)
            text,metadata=llm.generate('interpretation',{'code':'P0301'})
            self.assertAlmostEqual(metadata['cost_usd'],.000024)
            self.assertEqual(metadata['cached_tokens'],40)
            self.assertEqual(client.call_args.kwargs['base_url'],'https://openrouter.ai/api/v1')
            self.assertNotIn('test-only',str(metadata))

    def test_missing_usage_stays_unknown(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-only'}),patch('app.llm.OpenAI') as client:
            client.return_value.chat.completions.create.return_value=self.response()
            _,metadata=llm.generate('recherche',{})
            self.assertIsNone(metadata['cost_usd'])
            self.assertIsNone(metadata['input_tokens'])

    def test_empty_answer_is_rejected(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-only'}),patch('app.llm.OpenAI') as client:
            client.return_value.chat.completions.create.return_value=self.response(text='')
            with self.assertRaises(ValueError):
                llm.generate('interpretation',{})

    def test_unconfigured_model_cost_is_not_invented(self):
        usage=SimpleNamespace(prompt_tokens=100,completion_tokens=20,prompt_tokens_details=None)
        with patch.dict(os.environ,{'LLM_MODEL':'unknown-model','OPENROUTER_API_KEY':'test-only'}),patch('app.llm.OpenAI') as client:
            client.return_value.chat.completions.create.return_value=self.response(usage=usage)
            _,metadata=llm.generate('interpretation',{})
            self.assertIsNone(metadata['cost_usd'])


if __name__=='__main__':
    unittest.main()
