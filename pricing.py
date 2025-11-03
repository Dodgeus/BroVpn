from typing import Tuple


class Pricing:
    """Класс для расчета цен и скидок"""
    
    BASE_PRICES = {
        'month': 120,
        '3months': 300,
        '6months': 550,
        'year': 1000
    }
    
    DEVICE_MULTIPLIER = 0.05  # +5% за каждое дополнительное устройство
    
    @staticmethod
    def calculate_base_price(plan_type: str, device_count: int) -> float:
        """Рассчитать базовую цену без скидок"""
        base = Pricing.BASE_PRICES.get(plan_type, 120)
        
        # Первое устройство бесплатно, каждое следующее +5%
        if device_count > 1:
            multiplier = 1 + (device_count - 1) * Pricing.DEVICE_MULTIPLIER
            return base * multiplier
        
        return base
    
    @staticmethod
    def calculate_final_price(base_price: float, user_discount: float = 0.0, referrer_discount: float = 0.0) -> Tuple[float, float]:
        """Рассчитать финальную цену с учетом скидок
        
        Returns:
            Tuple[final_price, total_discount_amount]
        """
        # Применяем скидку реферала (10% для того, кто использует промокод)
        price_after_referrer = base_price * (1 - referrer_discount)
        
        # Применяем скидку владельца промокода (до 100%)
        final_price = price_after_referrer * (1 - user_discount)
        
        total_discount = base_price - final_price
        
        return round(final_price, 2), round(total_discount, 2)
    
    @staticmethod
    def get_plan_name(plan_type: str) -> str:
        """Получить название тарифа"""
        names = {
            'month': 'Месяц',
            '3months': '3 месяца',
            '6months': '6 месяцев',
            'year': 'Год'
        }
        return names.get(plan_type, plan_type)

